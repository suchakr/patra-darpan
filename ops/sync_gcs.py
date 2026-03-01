# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "google-cloud-storage",
# ]
# ///
"""
sync_gcs.py — Sync local corpus/ to GCS bucket cahcblr-pdfs

Syncs two prefixes:
  corpus/ijhs/  → assets/ijhs/    (IJHS papers)
  corpus/other/ → assets/other/   (non-IJHS CAHC papers)

Usage:
  python ops/sync_gcs.py --diff          # dry-run: show what would change
  python ops/sync_gcs.py                 # upload new/changed files
  python ops/sync_gcs.py --detailed      # show all files, not trimmed
"""
import os
import glob
import argparse
from google.cloud import storage

# Configuration
BUCKET_NAME = "cahcblr-pdfs"
PROJECT_ID = "gen-lang-client-0854320022"

# Local corpus directories → GCS prefixes
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..")

SYNC_MAP = [
    # (local_dir,                    gcs_prefix)
    (os.path.join(PROJECT_ROOT, "corpus/ijhs"),  "assets/ijhs/"),
    (os.path.join(PROJECT_ROOT, "corpus/other"), "assets/other/"),
]


def sync_gcs(force_yes=False, diff_only=False, delete_orphans=False, detailed=False):
    print(f"Connecting to GCS bucket: {BUCKET_NAME} in project {PROJECT_ID}...")

    try:
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)

        total_uploaded = 0
        total_orphans = 0

        for local_dir, gcs_prefix in SYNC_MAP:
            local_dir = os.path.abspath(local_dir)
            if not os.path.isdir(local_dir):
                print(f"\nSkipping {gcs_prefix} — local dir not found: {local_dir}")
                continue

            print(f"\n{'='*60}")
            print(f"Syncing: {local_dir} → gs://{BUCKET_NAME}/{gcs_prefix}")
            print(f"{'='*60}")

            # List GCS blobs
            blobs = list(bucket.list_blobs(prefix=gcs_prefix))
            remote_by_name = {os.path.basename(b.name): b for b in blobs if not b.name.endswith("/")}
            print(f"  GCS:   {len(remote_by_name)} files")

            # Scan local PDFs
            local_pdfs = []
            for f in os.listdir(local_dir):
                fp = os.path.join(local_dir, f)
                if os.path.isfile(fp) and f.lower().endswith(".pdf"):
                    local_pdfs.append((f, fp))
            print(f"  Local: {len(local_pdfs)} PDFs")

            # Diff
            to_upload = []
            up_to_date = 0

            for filename, abs_path in local_pdfs:
                if filename in remote_by_name:
                    blob = remote_by_name[filename]
                    if blob.size == os.path.getsize(abs_path):
                        up_to_date += 1
                    else:
                        to_upload.append(("UPDATE", filename, abs_path))
                else:
                    to_upload.append(("NEW", filename, abs_path))

            # Orphans: in GCS but not local
            local_names = {f for f, _ in local_pdfs}
            orphans = [(name, blob) for name, blob in remote_by_name.items()
                       if name not in local_names]

            print(f"\n  Up-to-date:    {up_to_date}")
            print(f"  Pending upload: {len(to_upload)}")
            print(f"  GCS orphans:    {len(orphans)}")

            if to_upload:
                new_count = len([x for x in to_upload if x[0] == "NEW"])
                upd_count = len([x for x in to_upload if x[0] == "UPDATE"])
                print(f"    [NEW]    {new_count}")
                print(f"    [UPDATE] {upd_count}")
                limit = None if detailed else 10
                for action, name, _ in (to_upload[:limit] if limit else to_upload):
                    print(f"    [{action}] {name}")
                if not detailed and len(to_upload) > 10:
                    print(f"    ... and {len(to_upload) - 10} more")

            if orphans:
                print("  Orphans:")
                limit = None if detailed else 10
                for name, _ in (orphans[:limit] if limit else orphans):
                    print(f"    [ORPHAN] {name}")
                if not detailed and len(orphans) > 10:
                    print(f"    ... and {len(orphans) - 10} more")

            if diff_only:
                continue

            # Upload
            if to_upload:
                if not force_yes:
                    resp = input(f"\n  Upload {len(to_upload)} files to {gcs_prefix}? [y/N]: ")
                    if resp.lower() != "y":
                        print("  Upload skipped.")
                        continue
                for action, filename, abs_path in to_upload:
                    target = f"{gcs_prefix}{filename}"
                    print(f"  ({action}) Uploading: {target}")
                    blob = bucket.blob(target)
                    blob.upload_from_filename(abs_path)
                    total_uploaded += 1

            # Delete orphans
            if orphans and delete_orphans:
                if not force_yes:
                    resp = input(f"\n  Delete {len(orphans)} orphans from {gcs_prefix}? [y/N]: ")
                    if resp.lower() != "y":
                        print("  Deletion skipped.")
                        continue
                for name, blob in orphans:
                    print(f"  (DELETE) {gcs_prefix}{name}")
                    blob.delete()
                    total_orphans += 1

        print(f"\n{'='*60}")
        print(f"Done. Uploaded: {total_uploaded}  Deleted: {total_orphans}")

    except Exception as e:
        print(f"Error: {e}")
        print("\nIf you see a 403 or Auth error, ensure you have run:")
        print("  gcloud auth application-default login")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync corpus/ PDFs to GCS bucket.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ops/sync_gcs.py --diff            # See what's pending
  python ops/sync_gcs.py                   # Upload interactively
  python ops/sync_gcs.py -y                # Upload without prompts
  python ops/sync_gcs.py --delete-orphans  # Also remove GCS orphans
"""
    )
    parser.add_argument("-y", "--yes", action="store_true", help="Bypass confirmation prompts.")
    parser.add_argument("--diff", action="store_true", help="Dry-run: only show differences.")
    parser.add_argument("--detailed", action="store_true", help="Show all files (no trimming).")
    parser.add_argument("--delete-orphans", action="store_true", help="Delete GCS files missing locally.")

    args = parser.parse_args()

    sync_gcs(
        force_yes=args.yes,
        diff_only=args.diff,
        delete_orphans=args.delete_orphans,
        detailed=args.detailed,
    )
