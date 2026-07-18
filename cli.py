import argparse
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from engine import (
    EXTRACTION_WORKERS,
    IMAGE_EXTENSIONS,
    NAMED_TEMPLATES,
    PROMPT_PROFILES,
    VIDEO_EXTENSIONS,
    CASE_STYLE_OPTIONS,
    ExifToolSession,
    _format_ai_error,
    analyze_asset_with_ai,
    apply_case_style,
    apply_naming_template,
    detect_hw_accel,
    execute_commit,
    export_staging_csv,
    import_staging_csv,
    is_already_processed,
    log_event,
    process_image_to_base64,
    process_video_to_base64,
    sanitize_name,
    set_active_profile,
    setup_logging,
    truncate_filename,
    validate_category,
)



# -----------------------------------------------------------------------------
# Thread-local ExifTool sessions for parallel commit workers
# -----------------------------------------------------------------------------

_commit_thread_local = threading.local()
_worker_sessions = []
_worker_sessions_lock = threading.Lock()


def _init_commit_worker():
    session = ExifToolSession()
    _commit_thread_local.exif_session = session
    with _worker_sessions_lock:
        _worker_sessions.append(session)


def _parallel_execute_commit(args):
    asset, target_dir, sort_into_folders, skip_rename = args
    session = _commit_thread_local.exif_session
    result = execute_commit(asset, target_dir, sort_into_folders, session, skip_rename=skip_rename)
    return asset, result


def _close_all_worker_sessions():
    with _worker_sessions_lock:
        for session in _worker_sessions:
            session.close()
        _worker_sessions.clear()


# -----------------------------------------------------------------------------
# Helper: sanitize category input
# -----------------------------------------------------------------------------

def _sanitize_category(raw):
    safe = "".join([c for c in raw.lower() if c.isalpha() or c.isdigit() or c in ("_", "-")]).strip("_")
    return safe if safe else None


# -----------------------------------------------------------------------------
# MAIN CLI PIPELINE
# -----------------------------------------------------------------------------

def process_library(directory_path, verbose=False, template_string=None, workers=None,
                    profile=None, case_style="snake_case", max_chars=0, force=False,
                    export_csv=None, import_csv=None, dry_run=False, metadata_only=False):
    extraction_workers = workers if workers is not None else EXTRACTION_WORKERS
    if profile:
        set_active_profile(profile)
    target_dir = Path(directory_path)
    if not target_dir.exists():
        print(f"Error: Directory '{directory_path}' does not exist.")
        sys.exit(1)

    logger = setup_logging(verbose=verbose)
    log_event(logger, "INFO", "session_start", details={
        "directory": directory_path, "verbose": verbose,
        "case_style": case_style, "max_chars": max_chars,
        "force": force, "dry_run": dry_run,
    })

    valid_exts = VIDEO_EXTENSIONS + IMAGE_EXTENSIONS

    # ------------------------------------------------------------------
    # CSV import path: skip extraction + analysis, load staging from file
    # ------------------------------------------------------------------
    if import_csv:
        import_path = Path(import_csv)
        if not import_path.exists():
            print(f"Error: Import CSV '{import_csv}' not found.")
            sys.exit(1)
        csv_text = import_path.read_text(encoding="utf-8")
        imported, warnings = import_staging_csv(csv_text, [])
        if warnings:
            for w in warnings:
                print(f"  Warning: {w}")
        if not imported:
            print("No assets found in CSV. Exiting.")
            return
        staged_assets = []
        for a in imported:
            fp = target_dir / a["original_name"]
            staged_assets.append({
                "original_path": fp if fp.exists() else None,
                "original_name": a["original_name"],
                "staged_name": a["staged_name"],
                "category": a["category"],
                "tags": a["tags"],
                "summary": a["summary"],
                "topic": "",
                "description": "",
            })
        print(f"Loaded {len(staged_assets)} assets from CSV '{import_csv}'.")
        if any(a["original_path"] is None for a in staged_assets):
            missing = [a["original_name"] for a in staged_assets if a["original_path"] is None]
            print(f"  Warning: {len(missing)} file(s) not found on disk — commit will fail for those.")
            for m in missing:
                print(f"    - {m}")
        # Skip to Phase 3
        _run_staging_phase(staged_assets, target_dir, logger, exif_session=None,
                           template_string=template_string, case_style=case_style,
                           max_chars=max_chars, dry_run=dry_run, metadata_only=metadata_only)
        return

    # ------------------------------------------------------------------
    # Standard path: extraction + analysis
    # ------------------------------------------------------------------
    asset_files = [f for f in target_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_exts]
    if not asset_files:
        print("Empty queue. No matching video or image wrappers detected.")
        log_event(logger, "INFO", "session_end", details={"reason": "no_matching_files"})
        return

    print("Initializing High-Performance Pipeline...")

    exif_session = ExifToolSession()

    hw_accel = detect_hw_accel()
    if hw_accel:
        print(f"Hardware Acceleration Enabled: FFmpeg will use '{hw_accel}' for fast video decoding.")
    else:
        print("Hardware Acceleration Not Found: Utilizing CPU fallback.")

    print(f"Scanning library: Found {len(asset_files)} assets.")
    print("-" * 85)

    # Phase 1: Parallel frame extraction
    pending_assets = []
    print("Phase 1: Extracting preview frames...")

    with ThreadPoolExecutor(max_workers=extraction_workers) as executor:
        future_to_file = {}
        for file in asset_files:
            if force or not is_already_processed(file, exif_session):
                if file.suffix.lower() in VIDEO_EXTENSIONS:
                    future = executor.submit(process_video_to_base64, file, hw_accel)
                else:
                    future = executor.submit(process_image_to_base64, file)
                future_to_file[future] = file
            else:
                print(f"Skipped (Already Processed): {file.name}")
                log_event(logger, "INFO", "file_skipped", file_name=file.name, details={"reason": "already_processed"})

        for future in as_completed(future_to_file):
            file = future_to_file[future]
            base64_data = future.result()
            if base64_data:
                pending_assets.append((file, base64_data))
            else:
                print(f"Failed to extract preview: {file.name}")
                log_event(logger, "ERROR", "extraction_failed", file_name=file.name)

    if not pending_assets:
        print("\nAll assets in directory are already tagged and processed. Exiting.")
        log_event(logger, "INFO", "session_end", details={"reason": "all_already_processed"})
        exif_session.close()
        return

    # Phase 2: Sequential AI Processing
    staged_assets = []
    print("\nPhase 2: Analyzing content with AI model...")

    for idx, (file_path, base64_img) in enumerate(pending_assets, 1):
        print(f"[{idx}/{len(pending_assets)}] AI analyzing: {file_path.name}...", end="", flush=True)

        ai_result = analyze_asset_with_ai(base64_img, verbose=verbose)

        if not ai_result['ok']:
            error_msg = _format_ai_error(ai_result, verbose=verbose)
            print(f" [{error_msg}]")
            log_event(logger, "ERROR", "ai_analysis_failed", file_name=file_path.name, details={"error": error_msg})
            continue

        ai_data = ai_result['data']
        safe_name = sanitize_name(ai_data['new_filename'])

        staged_category, category_fallback = validate_category(ai_data.get('suggested_category'))
        if category_fallback:
            original = ai_data.get('suggested_category', '(missing)')
            if verbose:
                print(f" [category fallback: {original!r} -> uncategorized]", end="")
            else:
                print(" [category: uncategorized]", end="")

        topic = ai_data.get('topic', '')
        description = ai_data.get('description', '')

        staged_assets.append({
            "original_path": file_path,
            "original_name": file_path.name,
            "staged_name": safe_name,
            "category": staged_category,
            "tags": ai_data.get('tags', []),
            "summary": ai_data.get('overall_visual_summary', ''),
            "topic": topic,
            "description": description,
            "base64_data": base64_img,
        })

        if template_string:
            rendered = apply_naming_template(template_string, {
                "category": staged_category,
                "topic": topic,
                "description": description,
                "new_filename": safe_name,
            })
            rendered = apply_case_style(rendered, case_style)
            rendered = truncate_filename(rendered, max_chars)
            staged_assets[-1]["staged_name"] = rendered
            safe_name = rendered

        print(f"  Staged as: {safe_name}")
        log_event(logger, "INFO", "ai_analysis_success", file_name=file_path.name, details={
            "staged_name": safe_name,
            "category": staged_category,
            "category_fallback": category_fallback,
            "tags_count": len(ai_data.get('tags', []))
        })

    if not staged_assets:
        print("\nNo assets were successfully staged. Exiting.")
        exif_session.close()
        return

    # CSV export (after Phase 2, before commit)
    if export_csv:
        csv_data = export_staging_csv(staged_assets)
        export_path = Path(export_csv)
        export_path.write_text(csv_data, encoding="utf-8")
        print(f"\nExported staging to '{export_csv}' ({len(staged_assets)} assets).")

    # Phase 3: Summary & interactive staging
    _run_staging_phase(staged_assets, target_dir, logger, exif_session,
                       template_string, case_style, max_chars, dry_run,
                       metadata_only=metadata_only)
    exif_session.close()


# -----------------------------------------------------------------------------
# Staging phase: summary, override, commit
# -----------------------------------------------------------------------------

def _run_staging_phase(staged_assets, target_dir, logger, exif_session,
                       template_string, case_style, max_chars, dry_run,
                       metadata_only=False):
    print("\n" + "=" * 85)
    print("AI STAGING MATRIX SUMMARY VIEW")
    print("=" * 85)
    for i, asset in enumerate(staged_assets, 1):
        suffix = asset["original_path"].suffix.lower() if asset["original_path"] else ""
        print(f"{i:2d}. [ORIGINAL] : {asset['original_name']}")
        print(f"    [PROPOSED] : {asset['staged_name']}{suffix}")
        print(f"    [CATEGORY] : {asset['category']}")
    print("=" * 85)

    sort_folders_input = input(
        "\nWould you like to sort these assets into categorized subfolders? [Y]es / [N]o: "
    ).strip().lower()
    sort_into_folders = sort_folders_input in ('y', 'yes')

    # Category override step for uncategorized assets
    uncategorized_assets = [a for a in staged_assets if a['category'] == 'uncategorized']
    if uncategorized_assets:
        print("\n" + "-" * 85)
        print("Category Override: Some assets fell back to 'uncategorized'.")
        print("   You can assign a custom category for each below (press Enter to skip).")
        print("-" * 85)
        for asset in uncategorized_assets:
            print(f"\n  Asset: {asset['original_name']}")
            print(f"  Proposed name: {asset['staged_name']}")
            custom_cat = input(f"  Custom category [{asset['category']}]: ").strip().lower()
            if custom_cat:
                safe_cat = _sanitize_category(custom_cat)
                if safe_cat:
                    asset['category'] = safe_cat
                    print(f"    -> Category set to: {safe_cat}")
                    log_event(logger, "INFO", "category_override", file_name=asset['original_name'],
                              details={"old_category": "uncategorized", "new_category": safe_cat})
                else:
                    print("    -> Invalid category name, keeping 'uncategorized'.")
            else:
                print("    -> Keeping 'uncategorized'.")

    # Execution path
    dry_run_label = " [DRY RUN — no files will be modified]" if dry_run else ""
    while True:
        choice = input(
            f"\nSelect execution path{dry_run_label} - "
            "[A]pply All, [I]nteractive, [D]ry-run preview"
            + ("" if dry_run else ", [C]ancel")
            + ": "
        ).strip().lower()

        if choice == 'c' and not dry_run:
            print("\nSession canceled safely. No assets were modified.")
            log_event(logger, "INFO", "session_end", details={"reason": "cancelled", "staged": len(staged_assets)})
            break

        elif choice == 'a' or (dry_run and choice == 'a'):
            _commit_all(staged_assets, target_dir, sort_into_folders, logger, dry_run,
                        metadata_only=metadata_only)
            break

        elif choice == 'i' or (dry_run and choice == 'i'):
            _interactive_commit(staged_assets, target_dir, sort_into_folders, logger,
                                exif_session, template_string, case_style, max_chars, dry_run,
                                metadata_only=metadata_only)
            break

        elif choice == 'd':
            _preview_dry_run(staged_assets, target_dir, sort_into_folders)
            break

        else:
            print("Invalid command. Type 'A', 'I', or 'D'" + (", 'C' to cancel." if not dry_run else "."))


# -----------------------------------------------------------------------------
# Apply All (batch commit)
# -----------------------------------------------------------------------------

def _commit_all(staged_assets, target_dir, sort_into_folders, logger, dry_run,
                metadata_only=False):
    if dry_run:
        print("\n[DRY RUN] Previewing batch commit...")
        _preview_dry_run(staged_assets, target_dir, sort_into_folders)
        return

    print("\nWriting metadata tags to files (parallel)...")
    commit_args = [(asset, target_dir, sort_into_folders, metadata_only) for asset in staged_assets]
    max_workers = min(len(commit_args), os.cpu_count() or 4)
    committed_count = 0
    with ThreadPoolExecutor(max_workers=max_workers, initializer=_init_commit_worker) as executor:
        futures = {executor.submit(_parallel_execute_commit, args): args[0] for args in commit_args}
        for future in as_completed(futures):
            asset, final_rel_path = future.result()
            if final_rel_path:
                print(f"Committed: {asset['original_name']} -> {final_rel_path}")
                log_event(logger, "INFO", "file_committed", file_name=asset['original_name'],
                          details={"new_path": str(final_rel_path), "category": asset['category']})
                committed_count += 1
            else:
                log_event(logger, "ERROR", "file_commit_failed", file_name=asset['original_name'])
    _close_all_worker_sessions()
    log_event(logger, "INFO", "session_end", details={
        "committed": committed_count, "total": len(staged_assets), "mode": "batch"
    })
    print("\nHigh-Performance Run Complete!")


# -----------------------------------------------------------------------------
# Interactive mode with per-asset review, re-analyze, bulk category
# -----------------------------------------------------------------------------

def _interactive_commit(staged_assets, target_dir, sort_into_folders, logger,
                        exif_session, template_string, case_style, max_chars, dry_run,
                        metadata_only=False):
    print("\nInteractive Mode. Review individual assets:")
    committed_count = 0
    skipped_count = 0
    reanalyzed_count = 0

    for idx, asset in enumerate(staged_assets, 1):
        print("\n" + "-" * 70)
        print(f"Asset [{idx}/{len(staged_assets)}]: {asset['original_name']}")
        print(f"Proposed Name   : {asset['staged_name']}")
        print(f"Target Category : {asset['category']}")
        tags_preview = ', '.join(asset['tags'][:8])
        if len(asset['tags']) > 8:
            tags_preview += "..."
        print(f"Search Keywords : {tags_preview}")
        print(f"Summary         : {asset['summary']}")
        print("-" * 70)

        prompt = (
            "[A]ccept / [S]kip / [R]e-analyze / [E]dit name"
            + (" / [B]ulk-apply category" if not dry_run else "")
            + ": "
        )
        sub_choice = input(prompt).strip().lower()

        if sub_choice in ('a', 'accept', ''):
            if dry_run:
                print(f"  [DRY RUN] Would commit: {asset['original_name']} -> {asset['staged_name']}")
                continue
            final_rel_path = execute_commit(asset, target_dir, sort_into_folders, exif_session,
                                             skip_rename=metadata_only)
            if final_rel_path:
                print(f"  Applied: {final_rel_path}")
                log_event(logger, "INFO", "file_committed", file_name=asset['original_name'],
                          details={"new_path": str(final_rel_path), "category": asset['category']})
                committed_count += 1

        elif sub_choice in ('s', 'skip', 'n', 'no'):
            print("  Asset skipped.")
            log_event(logger, "INFO", "file_skipped", file_name=asset['original_name'],
                      details={"reason": "user_skipped"})
            skipped_count += 1

        elif sub_choice in ('r', 'reanalyze', 're-analyze'):
            if "base64_data" not in asset:
                print("  Cannot re-analyze (no cached frame data). Skipping.")
                continue
            if dry_run:
                print("  [DRY RUN] Would re-analyze with AI.")
                continue
            print("  Re-analyzing with AI...", end="", flush=True)
            ai_result = analyze_asset_with_ai(asset["base64_data"], verbose=False)
            if ai_result['ok']:
                ai_data = ai_result['data']
                new_name = sanitize_name(ai_data['new_filename'])
                staged_category, _ = validate_category(ai_data.get('suggested_category'))
                asset['staged_name'] = new_name
                asset['category'] = staged_category
                asset['tags'] = ai_data.get('tags', [])
                asset['summary'] = ai_data.get('overall_visual_summary', '')
                asset['topic'] = ai_data.get('topic', '')
                asset['description'] = ai_data.get('description', '')
                if template_string:
                    rendered = apply_naming_template(template_string, {
                        "category": staged_category,
                        "topic": asset['topic'],
                        "description": asset['description'],
                        "new_filename": new_name,
                    })
                    rendered = apply_case_style(rendered, case_style)
                    rendered = truncate_filename(rendered, max_chars)
                    asset['staged_name'] = rendered
                log_event(logger, "INFO", "ai_analysis_success", file_name=asset['original_name'],
                          details={"staged_name": asset['staged_name'], "category": staged_category})
                print(f" updated -> {asset['staged_name']} [{staged_category}]")
                reanalyzed_count += 1
            else:
                print(f" failed: {_format_ai_error(ai_result)}")

        elif sub_choice in ('e', 'edit'):
            new_name = input(f"  Enter new name (without extension): ").strip().lower()
            if new_name:
                safe = sanitize_name(new_name)
                if safe:
                    asset['staged_name'] = safe
                    print(f"  Name updated to: {safe}")
                else:
                    print("  Invalid name, keeping original.")
            if not dry_run:
                final_rel_path = execute_commit(asset, target_dir, sort_into_folders, exif_session,
                                                 skip_rename=metadata_only)
                if final_rel_path:
                    print(f"  Applied: {final_rel_path}")
                    log_event(logger, "INFO", "file_committed", file_name=asset['original_name'],
                              details={"new_path": str(final_rel_path), "category": asset['category']})
                    committed_count += 1
            else:
                print(f"  [DRY RUN] Would commit: {asset['original_name']} -> {asset['staged_name']}")

        elif sub_choice in ('b', 'bulk') and not dry_run:
            bulk_cat = input("  Enter category name to apply to all remaining assets: ").strip().lower()
            safe_bulk = _sanitize_category(bulk_cat)
            if safe_bulk:
                for remaining in staged_assets[idx - 1:]:
                    remaining['category'] = safe_bulk
                log_event(logger, "INFO", "category_override",
                          details={"bulk_category": safe_bulk, "asset_count": len(staged_assets) - idx + 1})
                print(f"  Category '{safe_bulk}' applied to {len(staged_assets) - idx + 1} asset(s).")
                # Now commit this asset with the new category
                final_rel_path = execute_commit(asset, target_dir, sort_into_folders, exif_session,
                                                 skip_rename=metadata_only)
                if final_rel_path:
                    print(f"  Applied: {final_rel_path}")
                    log_event(logger, "INFO", "file_committed", file_name=asset['original_name'],
                              details={"new_path": str(final_rel_path), "category": safe_bulk})
                    committed_count += 1
            else:
                print("  Invalid category name, skipping.")

        else:
            if dry_run:
                print(f"  [DRY RUN] Would commit: {asset['original_name']} -> {asset['staged_name']}")
                continue
            # Treat anything else as a custom filename override
            safe_chars = [c for c in sub_choice.lower() if c.isalpha() or c.isdigit() or c in ('_', '-')]
            clean_override = "".join(safe_chars).strip('_')
            if clean_override:
                asset['staged_name'] = clean_override
                final_rel_path = execute_commit(asset, target_dir, sort_into_folders, exif_session,
                                                 skip_rename=metadata_only)
                if final_rel_path:
                    print(f"Applied Custom Override: {final_rel_path}")
                    log_event(logger, "INFO", "file_committed", file_name=asset['original_name'],
                              details={
                                  "new_path": str(final_rel_path), "category": asset['category'],
                                  "custom_name": clean_override,
                              })
                    committed_count += 1
            else:
                print("Invalid string input. Asset skipped.")

    log_event(logger, "INFO", "session_end", details={
        "committed": committed_count, "skipped": skipped_count,
        "reanalyzed": reanalyzed_count, "total": len(staged_assets), "mode": "interactive"
    })
    print(f"\nInteractive processing complete! {committed_count} committed, "
          f"{skipped_count} skipped, {reanalyzed_count} re-analyzed.")


# -----------------------------------------------------------------------------
# Dry-run preview
# -----------------------------------------------------------------------------

def _preview_dry_run(staged_assets, target_dir, sort_into_folders):
    print("\n" + "=" * 85)
    print("DRY-RUN PREVIEW — No files will be modified")
    print("=" * 85)
    for i, asset in enumerate(staged_assets, 1):
        suffix = asset["original_path"].suffix.lower() if asset["original_path"] else ""
        cat_subdir = asset["category"] if sort_into_folders else ""
        parts = [target_dir]
        if cat_subdir:
            parts.append(cat_subdir)
        parts.append(asset["staged_name"] + suffix)
        new_path = Path(*parts)
        print(f"{i:2d}. {asset['original_name']}")
        print(f"    -> {new_path}")
        print(f"    Category: {asset['category']}  |  Tags: {', '.join(asset['tags'][:5])}")
    print("=" * 85)
    print(f"Dry-run complete. {len(staged_assets)} assets ready. 0 files modified.")


# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Media Renamer — CLI Pipeline")
    parser.add_argument("dir", type=str, help="Path to target directory folder.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug output.")
    parser.add_argument(
        "--workers", "-w", type=int, default=None,
        help="Number of parallel extraction workers (default: cpu count or config value)."
    )
    parser.add_argument(
        "--profile", "-p", type=str, default=None,
        help=f"AI prompt profile: {', '.join(PROMPT_PROFILES.keys())} (default: config value)."
    )
    parser.add_argument(
        "--template", "-t", type=str, default=None,
        help='Naming template preset or raw pattern. '
             'Presets: default, short, editorial. '
             'Raw: e.g. "{date}_{category}_{topic}_{description}"'
    )
    parser.add_argument(
        "--case-style", "--style", type=str, default="snake_case",
        choices=CASE_STYLE_OPTIONS,
        help="Filename case style (default: snake_case)."
    )
    parser.add_argument(
        "--max-chars", "--max", type=int, default=0,
        help="Max filename characters (0 = no limit, default: 0)."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-analyze all files, including previously processed ones."
    )
    parser.add_argument(
        "--export-csv", type=str, default=None,
        metavar="FILE",
        help="Export staging data to CSV after analysis."
    )
    parser.add_argument(
        "--import-csv", type=str, default=None,
        metavar="FILE",
        help="Skip AI analysis and load staging from CSV file."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview commits without modifying any files."
    )
    parser.add_argument(
        "--metadata-only", action="store_true",
        help="Write metadata tags only — keep original filenames, no rename."
    )
    args = parser.parse_args()

    tmpl = args.template
    if tmpl and tmpl in NAMED_TEMPLATES:
        tmpl = NAMED_TEMPLATES[tmpl]

    process_library(
        args.dir, verbose=args.verbose, template_string=tmpl,
        workers=args.workers, profile=args.profile,
        case_style=args.case_style, max_chars=args.max_chars,
        force=args.force, export_csv=args.export_csv,
        import_csv=args.import_csv, dry_run=args.dry_run,
        metadata_only=args.metadata_only,
    )
