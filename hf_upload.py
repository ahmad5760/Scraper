import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

try:
    from huggingface_hub import CommitOperationAdd, HfApi
except ImportError as exc:
    raise SystemExit(
        "Missing dependency 'huggingface_hub'. Install it with: py -m pip install huggingface_hub"
    ) from exc


def load_local_env(env_path: Path = Path(".env")) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_local_env()


BATCH_SIZE = int(os.getenv("HF_BATCH_SIZE", "300"))
MAX_RETRIES = int(os.getenv("HF_UPLOAD_MAX_RETRIES", "5"))
INITIAL_BACKOFF_SECONDS = float(os.getenv("HF_UPLOAD_INITIAL_BACKOFF_SECONDS", "2"))
DEFAULT_DATASET_REPO_NAME = os.getenv("HF_DATASET_NAME", "fashion-product-images")
LOCAL_DATASET_DIR = Path(os.getenv("LOCAL_DATASET_DIR", "dataset"))
MANIFEST_PATH = LOCAL_DATASET_DIR / ".hf_upload_manifest.json"
LOG_PATH = LOCAL_DATASET_DIR / ".hf_upload_batches.jsonl"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
REQUIRE_METADATA = (os.getenv("HF_REQUIRE_METADATA", "true") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
}


@dataclass
class ImageRecord:
    keyword: str
    image_path: Path
    image_relative_path: str
    metadata_path: Path | None
    metadata_relative_path: str | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        with MANIFEST_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "schema_version": 1,
        "repo_id": "",
        "uploaded_images_by_keyword": {},
        "batch_history": [],
    }


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = MANIFEST_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=True, indent=2)
    tmp_path.replace(MANIFEST_PATH)


def append_batch_log(entry: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")


def get_token_from_env() -> str:
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
    if not token:
        raise RuntimeError("Missing HF_TOKEN (or HUGGINGFACE_HUB_TOKEN) in environment.")
    return token


def resolve_repo_id(api: HfApi) -> str:
    repo_from_env = (os.getenv("HF_DATASET_REPO") or "").strip()
    if repo_from_env:
        if "/" in repo_from_env:
            return repo_from_env
        username = api.whoami()["name"]
        return f"{username}/{repo_from_env}"

    username = api.whoami()["name"]
    return f"{username}/{DEFAULT_DATASET_REPO_NAME}"


def is_private_repo_requested() -> bool:
    raw = (os.getenv("HF_DATASET_PRIVATE", "true") or "").strip().lower()
    return raw in {"1", "true", "yes", "y"}


def collect_pending_images(manifest: dict) -> List[ImageRecord]:
    uploaded_index: Dict[str, set] = {}
    for keyword, rel_paths in manifest.get("uploaded_images_by_keyword", {}).items():
        uploaded_index[keyword] = set(rel_paths)

    records: List[ImageRecord] = []
    if not LOCAL_DATASET_DIR.exists():
        return records

    for keyword_dir in sorted([p for p in LOCAL_DATASET_DIR.iterdir() if p.is_dir()]):
        keyword = keyword_dir.name
        known_uploaded = uploaded_index.get(keyword, set())

        image_files = sorted(
            [
                p
                for p in keyword_dir.iterdir()
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
            ],
            key=lambda p: p.name.lower(),
        )

        skipped_missing_metadata = 0
        for image_path in image_files:
            rel_image = image_path.relative_to(LOCAL_DATASET_DIR).as_posix()
            if rel_image in known_uploaded:
                continue

            metadata_path = image_path.with_suffix(".json")
            has_metadata = metadata_path.exists()
            if REQUIRE_METADATA and not has_metadata:
                skipped_missing_metadata += 1
                continue

            metadata_rel = (
                metadata_path.relative_to(LOCAL_DATASET_DIR).as_posix() if has_metadata else None
            )
            records.append(
                ImageRecord(
                    keyword=keyword,
                    image_path=image_path,
                    image_relative_path=rel_image,
                    metadata_path=metadata_path if has_metadata else None,
                    metadata_relative_path=metadata_rel,
                )
            )
        if skipped_missing_metadata:
            print(
                f"Skipped {skipped_missing_metadata} image(s) in '{keyword}' "
                f"because matching .json metadata was not found."
            )

    return records


def chunk_records(records: List[ImageRecord], size: int) -> List[List[ImageRecord]]:
    return [records[i : i + size] for i in range(0, len(records), size)]


def build_commit_operations(records: List[ImageRecord]) -> tuple[list, list]:
    operations = []
    uploaded_paths: List[str] = []

    for record in records:
        operations.append(
            CommitOperationAdd(
                path_in_repo=record.image_relative_path,
                path_or_fileobj=str(record.image_path),
            )
        )
        uploaded_paths.append(record.image_relative_path)

        if record.metadata_path and record.metadata_relative_path:
            operations.append(
                CommitOperationAdd(
                    path_in_repo=record.metadata_relative_path,
                    path_or_fileobj=str(record.metadata_path),
                )
            )
            uploaded_paths.append(record.metadata_relative_path)

    return operations, uploaded_paths


def verify_remote_upload(api: HfApi, repo_id: str, uploaded_paths: List[str]) -> None:
    check_attempts = 4
    for attempt in range(1, check_attempts + 1):
        remote_paths = set(api.list_repo_files(repo_id=repo_id, repo_type="dataset"))
        missing = [path for path in uploaded_paths if path not in remote_paths]
        if not missing:
            return
        if attempt < check_attempts:
            time.sleep(2 * attempt)
        else:
            sample = ", ".join(missing[:5])
            raise RuntimeError(
                f"Remote verification failed. Missing {len(missing)} file(s), e.g. {sample}"
            )


def delete_local_files(records: List[ImageRecord]) -> None:
    for record in records:
        if record.image_path.exists():
            record.image_path.unlink()
        if record.metadata_path and record.metadata_path.exists():
            record.metadata_path.unlink()

    for keyword_dir in sorted([p for p in LOCAL_DATASET_DIR.iterdir() if p.is_dir()]):
        try:
            if not any(keyword_dir.iterdir()):
                keyword_dir.rmdir()
        except OSError:
            pass


def process_batch(
    api: HfApi,
    repo_id: str,
    batch_id: str,
    records: List[ImageRecord],
    manifest: dict,
    dry_run: bool,
) -> bool:
    operations, uploaded_paths = build_commit_operations(records)
    entry_base = {
        "timestamp_utc": utc_now_iso(),
        "batch_id": batch_id,
        "repo_id": repo_id,
        "image_count": len(records),
        "file_count": len(uploaded_paths),
    }

    if dry_run:
        dry_entry = {
            **entry_base,
            "status": "dry_run",
            "attempts": 0,
            "message": "No upload attempted.",
        }
        append_batch_log(dry_entry)
        print(
            f"[DRY RUN] Batch {batch_id}: {len(records)} images, {len(uploaded_paths)} files"
        )
        return True

    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            api.create_commit(
                repo_id=repo_id,
                repo_type="dataset",
                operations=operations,
                commit_message=f"Batch upload {batch_id}: {len(records)} images",
            )
            verify_remote_upload(api, repo_id, uploaded_paths)

            for record in records:
                bucket = manifest["uploaded_images_by_keyword"].setdefault(record.keyword, [])
                if record.image_relative_path not in bucket:
                    bucket.append(record.image_relative_path)

            manifest["batch_history"].append(
                {
                    "batch_id": batch_id,
                    "timestamp_utc": utc_now_iso(),
                    "image_count": len(records),
                    "status": "success",
                }
            )
            save_manifest(manifest)
            delete_local_files(records)

            success_entry = {
                **entry_base,
                "status": "success",
                "attempts": attempt,
            }
            append_batch_log(success_entry)
            print(
                f"Batch {batch_id} uploaded successfully "
                f"({len(records)} images, attempt {attempt})."
            )
            return True
        except Exception as exc:
            last_error = str(exc)
            if attempt < MAX_RETRIES:
                delay = INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
                print(
                    f"Batch {batch_id} failed on attempt {attempt}/{MAX_RETRIES}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
            else:
                failed_entry = {
                    **entry_base,
                    "status": "failed",
                    "attempts": attempt,
                    "error": last_error,
                }
                append_batch_log(failed_entry)
                print(f"Batch {batch_id} failed permanently: {last_error}")
                return False

    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload local scraped images to a HuggingFace dataset repo in batches."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and log batches without uploading or deleting local files.",
    )
    args = parser.parse_args()

    token = get_token_from_env()
    api = HfApi(token=token)

    repo_id = resolve_repo_id(api)
    api.create_repo(
        repo_id=repo_id,
        repo_type="dataset",
        private=is_private_repo_requested(),
        exist_ok=True,
    )
    print(f"Using dataset repo: {repo_id}")
    print(f"Local dataset directory: {LOCAL_DATASET_DIR.resolve()}")
    print(f"Batch size: {BATCH_SIZE}")

    manifest = load_manifest()
    if not manifest.get("repo_id"):
        manifest["repo_id"] = repo_id
        save_manifest(manifest)
    elif manifest["repo_id"] != repo_id:
        print(
            "Warning: existing manifest repo_id differs from current target. "
            f"Manifest has '{manifest['repo_id']}', current is '{repo_id}'."
        )

    pending = collect_pending_images(manifest)
    if not pending:
        print("No pending images found to upload.")
        return

    batches = chunk_records(pending, BATCH_SIZE)
    print(f"Pending images: {len(pending)} across {len(batches)} batch(es).")

    for index, batch in enumerate(batches, start=1):
        batch_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{index:04d}"
        ok = process_batch(
            api=api,
            repo_id=repo_id,
            batch_id=batch_id,
            records=batch,
            manifest=manifest,
            dry_run=args.dry_run,
        )
        if not ok:
            print("Stopping because the latest batch failed.")
            break


if __name__ == "__main__":
    main()
