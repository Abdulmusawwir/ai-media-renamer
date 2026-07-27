from __future__ import annotations

import argparse
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

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
    flush_telemetry,
    import_staging_csv,
    is_already_processed,
    log_commit_batch,
    log_event,
    normalize_category,
    process_image_to_base64,
    process_video_to_base64,
    sanitize_name,
    set_active_profile,
    setup_logging,
    track_event,
    truncate_filename,
    restore_default_config,
    validate_category,
)

try:
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

_show_progress = True



# -----------------------------------------------------------------------------
# Thread-local ExifTool sessions for parallel commit workers
# -----------------------------------------------------------------------------

_commit_thread_local = threading.local()
_worker_sessions = []
_worker_sessions_lock = threading.Lock()


def _init_commit_worker() -> None:
    """Initialize an ExifTool session for the current commit worker thread."""
    session = ExifToolSession()
    _commit_thread_local.exif_session = session
    with _worker_sessions_lock:
        _worker_sessions.append(session)


def _parallel_execute_commit(args: tuple[dict[str, Any], Path, bool, bool]) -> tuple[dict[str, Any], Any]:
    """Execute a commit for a single asset using the thread-local ExifTool session.

    Args:
        args: Tuple of (asset dict, target directory, sort_into_folders flag, skip_rename flag).

    Returns:
        Tuple of (asset dict, commit result path or None).
    """
    asset, target_dir, sort_into_folders, skip_rename = args
    session = _commit_thread_local.exif_session
    result = execute_commit(asset, target_dir, sort_into_folders, session, skip_rename=skip_rename)
    return asset, result


def _close_all_worker_sessions() -> None:
    """Close all ExifTool sessions created by commit worker threads."""
    with _worker_sessions_lock:
        for session in _worker_sessions:
            session.close()
        _worker_sessions.clear()


# -----------------------------------------------------------------------------
# Helper: sanitize category input
# -----------------------------------------------------------------------------

def _sanitize_category(raw: str) -> str | None:
    """Sanitize a raw category string via shared normalize_category().

    Args:
        raw: The raw category string input by the user.

    Returns:
        The sanitized category string, or None if the result is empty.
    """
    safe = normalize_category(raw)
    return safe if safe else None


# -----------------------------------------------------------------------------
# MAIN CLI PIPELINE
# -----------------------------------------------------------------------------

def process_library(
    directory_path: str,
    verbose: bool = False,
    template_string: str | None = None,
    workers: int | None = None,
    profile: str | None = None,
    case_style: str = "snake_case",
    max_chars: int = 0,
    force: bool = False,
    export_csv: str | None = None,
    import_csv: str | None = None,
    dry_run: bool = False,
    metadata_only: bool = False,
    recursive: bool = False,
    non_interactive: bool = False,
    categories_override: dict[str, str] | None = None,
    output_file: str | None = None,
    show_progress: bool = True,
) -> None:
    """Run the full AI media renaming pipeline on a directory.

    Orchestrates extraction, AI analysis, staging, and commit phases
    for all supported media files in the target directory.

    Args:
        directory_path: Path to the target media directory.
        verbose: Enable debug-level logging output.
        template_string: Naming template preset or raw pattern string.
        workers: Number of parallel extraction workers (None uses default).
        profile: AI prompt profile name to use for analysis.
        case_style: Filename case style (e.g. snake_case, kebab-case).
        max_chars: Maximum filename character length (0 = no limit).
        force: Re-analyze all files, including previously processed ones.
        export_csv: Path to export staging data as CSV after analysis.
        import_csv: Path to import staging data from CSV, skipping AI analysis.
        dry_run: Preview commits without modifying any files.
        metadata_only: Write metadata tags only, keep original filenames.
        recursive: Scan subdirectories recursively for media files.
        non_interactive: Skip all prompts, apply suggestions as-is.
        categories_override: Mapping of filenames to forced category strings.
        output_file: Path to write a JSON commit summary.
        show_progress: Show rich progress bars during execution.
    """
    global _show_progress
    _show_progress = show_progress and _HAS_RICH
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
    track_event("cli_session_started", {
        "case_style": case_style,
        "dry_run": dry_run,
        "force": force,
        "recursive": recursive,
        "has_profile": bool(profile),
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
    if recursive:
        asset_files = [f for f in target_dir.rglob("*") if f.is_file() and f.suffix.lower() in valid_exts]
    else:
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

    def _extract() -> None:
        nonlocal pending_assets
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

    if _show_progress:
        total_to_process = sum(1 for f in asset_files if force or not is_already_processed(f, exif_session))
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      BarColumn(), TaskProgressColumn()) as progress:
            task = progress.add_task("Phase 1: Extracting previews...", total=total_to_process)
            _extract()
            progress.update(task, completed=total_to_process)
    else:
        print("Phase 1: Extracting preview frames...")
        _extract()

    if not pending_assets:
        print("\nAll assets in directory are already tagged and processed. Exiting.")
        log_event(logger, "INFO", "session_end", details={"reason": "all_already_processed"})
        exif_session.close()
        return

    # Phase 2: Sequential AI Processing
    staged_assets = []

    def _analyze() -> None:
        nonlocal staged_assets
        for idx, (file_path, base64_img) in enumerate(pending_assets, 1):
            if _show_progress:
                progress.update(task, advance=0, description=f"Phase 2: Analyzing {file_path.name}...")
            else:
                print(f"[{idx}/{len(pending_assets)}] AI analyzing: {file_path.name}...", end="", flush=True)

            ai_result = analyze_asset_with_ai(base64_img, verbose=verbose)

            if not ai_result['ok']:
                error_msg = _format_ai_error(ai_result, verbose=verbose)
                if not _show_progress:
                    print(f" [{error_msg}]")
                log_event(logger, "ERROR", "ai_analysis_failed", file_name=file_path.name, details={"error": error_msg})
                if _show_progress:
                    progress.update(task, advance=1)
                continue

            ai_data = ai_result['data']
            safe_name = sanitize_name(ai_data['new_filename'])

            staged_category, category_fallback = validate_category(ai_data.get('suggested_category'))
            if category_fallback and not _show_progress:
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
                "audio_transcription": "",
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

            if not _show_progress:
                print(f"  Staged as: {safe_name}")
            log_event(logger, "INFO", "ai_analysis_success", file_name=file_path.name, details={
                "staged_name": safe_name,
                "category": staged_category,
                "category_fallback": category_fallback,
                "tags_count": len(ai_data.get('tags', []))
            })
            if _show_progress:
                progress.update(task, advance=1)

    task = None
    if _show_progress:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      BarColumn(), TaskProgressColumn()) as progress:
            task = progress.add_task("Phase 2: Analyzing with AI...", total=len(pending_assets))
            _analyze()
            progress.update(task, completed=len(pending_assets))
    else:
        print("\nPhase 2: Analyzing content with AI model...")
        _analyze()

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
                       metadata_only=metadata_only,
                       non_interactive=non_interactive,
                       categories_override=categories_override)
    exif_session.close()

    # Output summary file
    if output_file:
        import json as _json
        summary = {
            "total": len(staged_assets),
            "committed": sum(1 for a in staged_assets if a.get("commit_status") == "committed"),
            "failed": sum(1 for a in staged_assets if a.get("commit_status") == "failed"),
            "assets": [
                {"original": a["original_name"], "staged": a.get("staged_name", ""),
                 "category": a.get("category", ""), "status": a.get("commit_status", "pending")}
                for a in staged_assets
            ]
        }
        out_path = Path(output_file)
        out_path.write_text(_json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nCommit summary written to '{output_file}'.")


# -----------------------------------------------------------------------------
# Staging phase: summary, override, commit
# -----------------------------------------------------------------------------

def _run_staging_phase(
    staged_assets: list[dict[str, Any]],
    target_dir: Path,
    logger: Any,
    exif_session: Any,
    template_string: str | None,
    case_style: str,
    max_chars: int,
    dry_run: bool,
    metadata_only: bool = False,
    non_interactive: bool = False,
    categories_override: dict[str, str] | None = None,
) -> None:
    """Display the staging matrix and handle category overrides and commit execution.

    Args:
        staged_assets: List of staged asset dictionaries.
        target_dir: Target directory for file operations.
        logger: Logger instance for event logging.
        exif_session: ExifTool session for metadata writing.
        template_string: Naming template string for filename rendering.
        case_style: Filename case style for formatting.
        max_chars: Maximum filename character length.
        dry_run: Preview mode — do not modify files.
        metadata_only: Write metadata only, skip file renaming.
        non_interactive: Skip user prompts, apply defaults.
        categories_override: Mapping of filenames to forced categories.
    """
    print("\n" + "=" * 85)
    print("AI STAGING MATRIX SUMMARY VIEW")
    print("=" * 85)
    for i, asset in enumerate(staged_assets, 1):
        suffix = asset["original_path"].suffix.lower() if asset["original_path"] else ""
        print(f"{i:2d}. [ORIGINAL] : {asset['original_name']}")
        print(f"    [PROPOSED] : {asset['staged_name']}{suffix}")
        print(f"    [CATEGORY] : {asset['category']}")
    print("=" * 85)

    if non_interactive:
        sort_into_folders = False
        if categories_override:
            for asset in staged_assets:
                override = categories_override.get(asset["original_name"])
                if override:
                    safe_cat = _sanitize_category(override)
                    if safe_cat:
                        asset["category"] = safe_cat
                        print(f"  Override: {asset['original_name']} -> {safe_cat}")
        _commit_all(staged_assets, target_dir, sort_into_folders, logger, dry_run,
                    metadata_only=metadata_only)
        return

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

def _commit_all(
    staged_assets: list[dict[str, Any]],
    target_dir: Path,
    sort_into_folders: bool,
    logger: Any,
    dry_run: bool,
    metadata_only: bool = False,
) -> None:
    """Batch-commit all staged assets in parallel using worker threads.

    Args:
        staged_assets: List of staged asset dictionaries to commit.
        target_dir: Target directory for file operations.
        sort_into_folders: Whether to sort committed files into category subfolders.
        logger: Logger instance for event logging.
        dry_run: Preview mode — do not modify files.
        metadata_only: Write metadata only, skip file renaming.
    """
    if dry_run:
        print("\n[DRY RUN] Previewing batch commit...")
        _preview_dry_run(staged_assets, target_dir, sort_into_folders)
        return

    def _do_commit() -> None:
        nonlocal committed_count
        commit_args = [(asset, target_dir, sort_into_folders, metadata_only) for asset in staged_assets]
        max_workers = min(len(commit_args), os.cpu_count() or 4)
        with ThreadPoolExecutor(max_workers=max_workers, initializer=_init_commit_worker) as executor:
            futures = {executor.submit(_parallel_execute_commit, args): args[0] for args in commit_args}
            for future in as_completed(futures):
                asset, final_rel_path = future.result()
                if final_rel_path:
                    if not _show_progress:
                        print(f"Committed: {asset['original_name']} -> {final_rel_path}")
                    log_event(logger, "INFO", "file_committed", file_name=asset['original_name'],
                              details={"new_path": str(final_rel_path), "category": asset['category']})
                    committed_count += 1
                    new_path_resolved = target_dir / str(final_rel_path)
                    injected_tags = [
                        "XMP-dc:Title", "XMP-dc:Description", "Microsoft:Category", "XMP-dc:Subject",
                    ]
                    if asset["original_path"].suffix.lower() in VIDEO_EXTENSIONS:
                        injected_tags += [
                            "QuickTime:Title", "QuickTime:Description", "QuickTime:Comment",
                            "QuickTime:Keywords", "Keys:Description", "Keys:Keywords",
                        ]
                    else:
                        injected_tags += [
                            "EXIF:XPTitle", "EXIF:XPKeywords", "Description", "Comment", "Keywords",
                        ]
                    undo_records.append({
                        "original_path": str(asset["original_path"]),
                        "new_path": str(new_path_resolved),
                        "original_name": asset["original_name"],
                        "new_name": asset["staged_name"],
                        "category": asset["category"],
                        "tags": asset.get("tags", []),
                        "injected_tags": injected_tags,
                    })
                else:
                    log_event(logger, "ERROR", "file_commit_failed", file_name=asset['original_name'])
                if _show_progress:
                    progress.update(task, advance=1, description=f"Committing {asset['original_name']}...")

    committed_count = 0
    import uuid as _uuid
    batch_id = str(_uuid.uuid4())[:12]
    undo_records: list[dict] = []
    if _show_progress:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      BarColumn(), TaskProgressColumn()) as progress:
            task = progress.add_task("Phase 3: Committing...", total=len(staged_assets))
            _do_commit()
            progress.update(task, completed=len(staged_assets))
    else:
        print("\nWriting metadata tags to files (parallel)...")
        _do_commit()

    _close_all_worker_sessions()
    log_event(logger, "INFO", "session_end", details={
        "committed": committed_count, "total": len(staged_assets), "mode": "batch"
    })
    if undo_records:
        log_commit_batch(batch_id, str(target_dir), undo_records)
    track_event("cli_session_completed", {
        "committed": committed_count,
        "total": len(staged_assets),
        "mode": "batch",
    })
    flush_telemetry()
    print("\nHigh-Performance Run Complete!")


# -----------------------------------------------------------------------------
# Interactive mode with per-asset review, re-analyze, bulk category
# -----------------------------------------------------------------------------

def _interactive_commit(
    staged_assets: list[dict[str, Any]],
    target_dir: Path,
    sort_into_folders: bool,
    logger: Any,
    exif_session: Any,
    template_string: str | None,
    case_style: str,
    max_chars: int,
    dry_run: bool,
    metadata_only: bool = False,
) -> None:
    """Run interactive per-asset review with accept, skip, re-analyze, edit, and bulk-apply options.

    Args:
        staged_assets: List of staged asset dictionaries to review.
        target_dir: Target directory for file operations.
        sort_into_folders: Whether to sort committed files into category subfolders.
        logger: Logger instance for event logging.
        exif_session: ExifTool session for metadata writing.
        template_string: Naming template string for filename rendering.
        case_style: Filename case style for formatting.
        max_chars: Maximum filename character length.
        dry_run: Preview mode — do not modify files.
        metadata_only: Write metadata only, skip file renaming.
    """
    print("\nInteractive Mode. Review individual assets:")
    committed_count = 0
    skipped_count = 0
    reanalyzed_count = 0
    import uuid as _uuid
    batch_id = str(_uuid.uuid4())[:12]
    undo_records: list[dict] = []

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
                injected_tags = ["XMP-dc:Title", "XMP-dc:Description", "Microsoft:Category", "XMP-dc:Subject"]
                if asset["original_path"].suffix.lower() in VIDEO_EXTENSIONS:
                    injected_tags += ["QuickTime:Title", "QuickTime:Description", "QuickTime:Comment",
                                      "QuickTime:Keywords", "Keys:Description", "Keys:Keywords"]
                else:
                    injected_tags += ["EXIF:XPTitle", "EXIF:XPKeywords", "Description", "Comment", "Keywords"]
                undo_records.append({
                    "original_path": str(asset["original_path"]),
                    "new_path": str(target_dir / str(final_rel_path)),
                    "original_name": asset["original_name"],
                    "new_name": asset["staged_name"],
                    "category": asset["category"],
                    "tags": asset.get("tags", []),
                    "injected_tags": injected_tags,
                })

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
                    injected_tags = ["XMP-dc:Title", "XMP-dc:Description", "Microsoft:Category", "XMP-dc:Subject"]
                    if asset["original_path"].suffix.lower() in VIDEO_EXTENSIONS:
                        injected_tags += ["QuickTime:Title", "QuickTime:Description", "QuickTime:Comment",
                                          "QuickTime:Keywords", "Keys:Description", "Keys:Keywords"]
                    else:
                        injected_tags += ["EXIF:XPTitle", "EXIF:XPKeywords", "Description", "Comment", "Keywords"]
                    undo_records.append({
                        "original_path": str(asset["original_path"]),
                        "new_path": str(target_dir / str(final_rel_path)),
                        "original_name": asset["original_name"],
                        "new_name": asset["staged_name"],
                        "category": asset["category"],
                        "tags": asset.get("tags", []),
                        "injected_tags": injected_tags,
                    })
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
                    injected_tags = ["XMP-dc:Title", "XMP-dc:Description", "Microsoft:Category", "XMP-dc:Subject"]
                    if asset["original_path"].suffix.lower() in VIDEO_EXTENSIONS:
                        injected_tags += ["QuickTime:Title", "QuickTime:Description", "QuickTime:Comment",
                                          "QuickTime:Keywords", "Keys:Description", "Keys:Keywords"]
                    else:
                        injected_tags += ["EXIF:XPTitle", "EXIF:XPKeywords", "Description", "Comment", "Keywords"]
                    undo_records.append({
                        "original_path": str(asset["original_path"]),
                        "new_path": str(target_dir / str(final_rel_path)),
                        "original_name": asset["original_name"],
                        "new_name": asset["staged_name"],
                        "category": asset["category"],
                        "tags": asset.get("tags", []),
                        "injected_tags": injected_tags,
                    })
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
                    injected_tags = ["XMP-dc:Title", "XMP-dc:Description", "Microsoft:Category", "XMP-dc:Subject"]
                    if asset["original_path"].suffix.lower() in VIDEO_EXTENSIONS:
                        injected_tags += ["QuickTime:Title", "QuickTime:Description", "QuickTime:Comment",
                                          "QuickTime:Keywords", "Keys:Description", "Keys:Keywords"]
                    else:
                        injected_tags += ["EXIF:XPTitle", "EXIF:XPKeywords", "Description", "Comment", "Keywords"]
                    undo_records.append({
                        "original_path": str(asset["original_path"]),
                        "new_path": str(target_dir / str(final_rel_path)),
                        "original_name": asset["original_name"],
                        "new_name": asset["staged_name"],
                        "category": asset["category"],
                        "tags": asset.get("tags", []),
                        "injected_tags": injected_tags,
                    })
            else:
                print("Invalid string input. Asset skipped.")

    log_event(logger, "INFO", "session_end", details={
        "committed": committed_count, "skipped": skipped_count,
        "reanalyzed": reanalyzed_count, "total": len(staged_assets), "mode": "interactive"
    })
    if undo_records:
        log_commit_batch(batch_id, str(target_dir), undo_records)
    track_event("cli_session_completed", {
        "committed": committed_count,
        "skipped": skipped_count,
        "reanalyzed": reanalyzed_count,
        "total": len(staged_assets),
        "mode": "interactive",
    })
    flush_telemetry()
    print(f"\nInteractive processing complete! {committed_count} committed, "
          f"{skipped_count} skipped, {reanalyzed_count} re-analyzed.")


# -----------------------------------------------------------------------------
# Dry-run preview
# -----------------------------------------------------------------------------

def _preview_dry_run(
    staged_assets: list[dict[str, Any]],
    target_dir: Path,
    sort_into_folders: bool,
) -> None:
    """Print a dry-run preview showing what changes would be made without modifying files.

    Args:
        staged_assets: List of staged asset dictionaries to preview.
        target_dir: Target directory for resolving proposed paths.
        sort_into_folders: Whether to show category subfolder paths.
    """
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
    parser.add_argument(
        "-r", "--include-subdirectories", action="store_true",
        help="Scan subdirectories recursively for media files."
    )
    parser.add_argument(
        "-y", "--non-interactive", action="store_true",
        help="Non-interactive mode: skip all prompts, apply all suggestions as-is."
    )
    parser.add_argument(
        "--categories-override", type=str, default=None, metavar="FILE",
        help="JSON file mapping filenames to forced categories (used with -y)."
    )
    parser.add_argument(
        "--output", type=str, default=None, metavar="FILE",
        help="Write commit summary to a JSON file."
    )
    parser.add_argument(
        "--no-progress", action="store_true",
        help="Disable progress bars (for pipe-friendly output)."
    )
    parser.add_argument(
        "--rollback", action="store_true",
        help="Undo the last commit batch: move files back to original locations."
    )
    parser.add_argument(
        "--reset-config", action="store_true",
        help="Reset config.json to factory defaults and exit."
    )
    args = parser.parse_args()

    if args.rollback:
        from engine import rollback_last_batch as _rollback
        result = _rollback()
        if result["ok"]:
            print(f"Restored {result['restored']} files to original locations.")
        else:
            print(f"Restored {result['restored']}, failed {result['failed']}.")
            for err in result["errors"][:5]:
                print(f"  - {err}")
        sys.exit(0 if result["ok"] else 1)

    if args.reset_config:
        if restore_default_config():
            print("config.json has been restored to factory defaults.")
        else:
            print("Error: config.default.json not found. Cannot restore.")
        sys.exit(0)

    tmpl = args.template
    if tmpl and tmpl in NAMED_TEMPLATES:
        tmpl = NAMED_TEMPLATES[tmpl]

    categories_override = None
    if args.categories_override:
        import json as _json
        override_path = Path(args.categories_override)
        if not override_path.exists():
            print(f"Error: Categories override file '{args.categories_override}' not found.")
            sys.exit(1)
        categories_override = _json.loads(override_path.read_text(encoding="utf-8"))

    process_library(
        args.dir, verbose=args.verbose, template_string=tmpl,
        workers=args.workers, profile=args.profile,
        case_style=args.case_style, max_chars=args.max_chars,
        force=args.force, export_csv=args.export_csv,
        import_csv=args.import_csv, dry_run=args.dry_run,
        metadata_only=args.metadata_only,
        recursive=args.include_subdirectories,
        non_interactive=args.non_interactive,
        categories_override=categories_override,
        output_file=args.output,
        show_progress=not args.no_progress,
    )
