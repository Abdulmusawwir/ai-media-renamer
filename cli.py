import os
import sys
import argparse
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from engine import (
    load_config, config, ALLOWED_CATEGORIES, AI_PROMPT,
    VIDEO_EXTENSIONS, IMAGE_EXTENSIONS, MODEL_NAME,
    MODEL_TEMPERATURE, MODEL_NUM_CTX, MODEL_KEEP_ALIVE,
    IMAGE_PREVIEW_MAX_EDGE, LOG_DIR,
    setup_logging, log_event,
    ExifToolSession, detect_hw_accel, is_already_processed,
    process_video_to_base64, process_image_to_base64,
    validate_category, sanitize_name,
    analyze_asset_with_ai, _format_ai_error,
    execute_commit
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
    asset, target_dir, sort_into_folders = args
    session = _commit_thread_local.exif_session
    result = execute_commit(asset, target_dir, sort_into_folders, session)
    return asset, result


def _close_all_worker_sessions():
    with _worker_sessions_lock:
        for session in _worker_sessions:
            session.close()
        _worker_sessions.clear()


# -----------------------------------------------------------------------------
# MAIN CLI PIPELINE
# -----------------------------------------------------------------------------

def process_library(directory_path, verbose=False):
    target_dir = Path(directory_path)
    if not target_dir.exists():
        print(f"Error: Directory '{directory_path}' does not exist.")
        sys.exit(1)

    logger = setup_logging(verbose=verbose)
    log_event(logger, "INFO", "session_start", details={"directory": directory_path, "verbose": verbose})

    asset_files = [f for f in target_dir.iterdir() if f.is_file() and f.suffix.lower() in (VIDEO_EXTENSIONS + IMAGE_EXTENSIONS)]
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
    print("Phase 1: Checking caches and extracting grids into RAM...")

    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        future_to_file = {}
        for file in asset_files:
            if not is_already_processed(file, exif_session):
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
                print(f"Failed to extract into RAM: {file.name}")
                log_event(logger, "ERROR", "extraction_failed", file_name=file.name)

    if not pending_assets:
        print("\nAll assets in directory are already tagged and processed. Exiting.")
        log_event(logger, "INFO", "session_end", details={"reason": "all_already_processed"})
        exif_session.close()
        return

    # Phase 2: Sequential AI Processing
    staged_assets = []
    print("\nPhase 2: Injecting RAM streams directly into AI Vision Model...")

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
                print(f" [category: uncategorized]", end="")

        staged_assets.append({
            "original_path": file_path,
            "original_name": file_path.name,
            "staged_name": safe_name,
            "category": staged_category,
            "tags": ai_data.get('tags', []),
            "summary": ai_data.get('overall_visual_summary', '')
        })
        print(f" -> Staged: {safe_name}")
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

    # Phase 3: Summary & interactive staging
    print("\n" + "=" * 85)
    print("AI STAGING MATRIX SUMMARY VIEW")
    print("=" * 85)
    for i, asset in enumerate(staged_assets, 1):
        print(f"{i:2d}. [ORIGINAL] : {asset['original_name']}")
        print(f"    [PROPOSED] : {asset['staged_name']}{asset['original_path'].suffix.lower()}")
        print(f"    [CATEGORY] : {asset['category']}")
    print("=" * 85)

    sort_folders_input = input("\nWould you like to sort these assets into categorized subfolders? [Y]es / [N]o: ").strip().lower()
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
                safe_cat = "".join([c for c in custom_cat if c.isalpha() or c.isdigit() or c in ('_', '-')]).strip('_')
                if safe_cat:
                    asset['category'] = safe_cat
                    print(f"    -> Category set to: {safe_cat}")
                    log_event(logger, "INFO", "category_override", file_name=asset['original_name'],
                              details={"old_category": "uncategorized", "new_category": safe_cat})
                else:
                    print("    -> Invalid category name, keeping 'uncategorized'.")
            else:
                print("    -> Keeping 'uncategorized'.")

    while True:
        choice = input("\nSelect execution path - [A]pply All changes, [I]nteractive mode, [C]ancel session: ").strip().lower()

        if choice == 'c':
            print("\nSession canceled safely. No assets were modified.")
            log_event(logger, "INFO", "session_end", details={"reason": "cancelled", "staged": len(staged_assets)})
            break

        elif choice == 'a':
            print("\nPiping ExifTool commands directly into metadata containers (parallel)...")
            commit_args = [(asset, target_dir, sort_into_folders) for asset in staged_assets]
            max_workers = min(len(commit_args), os.cpu_count() or 4)
            committed_count = 0
            with ThreadPoolExecutor(max_workers=max_workers, initializer=_init_commit_worker) as executor:
                futures = {executor.submit(_parallel_execute_commit, args): args[0] for args in commit_args}
                for future in as_completed(futures):
                    asset, final_rel_path = future.result()
                    if final_rel_path:
                        print(f"Baked & Moved: {asset['original_name']} -> {final_rel_path}")
                        log_event(logger, "INFO", "file_committed", file_name=asset['original_name'],
                                  details={"new_path": str(final_rel_path), "category": asset['category']})
                        committed_count += 1
                    else:
                        log_event(logger, "ERROR", "file_commit_failed", file_name=asset['original_name'])
            _close_all_worker_sessions()
            log_event(logger, "INFO", "session_end", details={"committed": committed_count, "total": len(staged_assets), "mode": "batch"})
            print("\nHigh-Performance Run Complete!")
            break

        elif choice == 'i':
            print("\nInteractive Mode. Review individual assets:")
            committed_count = 0
            for idx, asset in enumerate(staged_assets, 1):
                print("\n" + "-" * 70)
                print(f"Asset [{idx}/{len(staged_assets)}]: {asset['original_name']}")
                print(f"Proposed Name   : {asset['staged_name']}")
                print(f"Target Category : {asset['category']}")
                print(f"Search Keywords : {', '.join(asset['tags'][:8])}...")
                print("-" * 70)

                sub_choice = input("Commit changes? [Y]es / [N]o to skip / [Type custom name to override]: ").strip()

                if sub_choice.lower() in ('y', 'yes', ''):
                    final_rel_path = execute_commit(asset, target_dir, sort_into_folders, exif_session)
                    if final_rel_path:
                        print(f"  Applied: {final_rel_path}")
                        log_event(logger, "INFO", "file_committed", file_name=asset['original_name'],
                                  details={"new_path": str(final_rel_path), "category": asset['category']})
                        committed_count += 1
                elif sub_choice.lower() in ('n', 'no'):
                    print("  Asset skipped.")
                    log_event(logger, "INFO", "file_skipped", file_name=asset['original_name'], details={"reason": "user_skipped"})
                else:
                    clean_override = "".join([c for c in sub_choice.lower() if c.isalpha() or c.isdigit() or c in ('_', '-')]).strip('_')
                    if clean_override:
                        asset['staged_name'] = clean_override
                        final_rel_path = execute_commit(asset, target_dir, sort_into_folders, exif_session)
                        if final_rel_path:
                            print(f"Applied Custom Override: {final_rel_path}")
                            log_event(logger, "INFO", "file_committed", file_name=asset['original_name'],
                                      details={"new_path": str(final_rel_path), "category": asset['category'], "custom_name": clean_override})
                            committed_count += 1
                    else:
                        print("Invalid string input. Asset skipped.")
            log_event(logger, "INFO", "session_end", details={"committed": committed_count, "total": len(staged_assets), "mode": "interactive"})
            print("\nInteractive processing run finalized!")
            break
        else:
            print("Invalid command. Type 'A', 'I', or 'C'.")

    exif_session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Video Renamer & ExifTool Engine")
    parser.add_argument("dir", type=str, help="Path to target directory folder.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug output.")
    args = parser.parse_args()

    process_library(args.dir, verbose=args.verbose)
