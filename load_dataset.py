import argparse
import os
from pathlib import Path

try:
    from huggingface_hub import HfApi, snapshot_download
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


def resolve_hf_token() -> str | None:
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
    return token.strip() if token else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download a full Hugging Face dataset repo snapshot to a local directory."
    )
    parser.add_argument(
        "--repo-id",
        default="Ahmad1931259/fashion-product-images",
        help="Dataset repository ID on Hugging Face.",
    )
    parser.add_argument(
        "--local-dir",
        default="load_dataset",
        help="Local output directory for the downloaded dataset snapshot.",
    )
    args = parser.parse_args()

    load_local_env()
    token = resolve_hf_token()
    local_dir = Path(args.local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    print(f"Preparing to download dataset: {args.repo_id}")
    print(f"Target directory: {local_dir.resolve()}")

    api = HfApi(token=token)
    try:
        repo_files = api.list_repo_files(repo_id=args.repo_id, repo_type="dataset")
        print(f"Remote file count: {len(repo_files)}")
    except Exception as exc:
        print(f"Warning: could not list remote files before download ({exc}).")

    snapshot_path = snapshot_download(
        repo_id=args.repo_id,
        repo_type="dataset",
        token=token,
        local_dir=str(local_dir),
    )

    print(f"Download complete. Snapshot path: {snapshot_path}")


if __name__ == "__main__":
    main()
