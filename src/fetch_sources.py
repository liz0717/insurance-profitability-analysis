"""Download configured public financial-report sources without an API."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "sources_2025.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "raw"
DEFAULT_MANIFEST = REPO_ROOT / "data" / "download_manifest_2025.csv"

REQUIRED_COLUMNS = {
    "source_id",
    "company_id",
    "source_title",
    "source_type",
    "source_url",
}

ALLOWED_SOURCE_TYPES = {"html", "pdf", "csv", "xlsx"}
EXTENSION_BY_TYPE = {
    "html": ".html",
    "pdf": ".pdf",
    "csv": ".csv",
    "xlsx": ".xlsx",
}

MANIFEST_COLUMNS = [
    "source_id",
    "company_id",
    "source_title",
    "configured_url",
    "final_url",
    "source_type",
    "content_type",
    "http_status",
    "download_status",
    "downloaded_at_utc",
    "local_path",
    "file_size_bytes",
    "sha256",
    "error",
]


def safe_path_part(value: str) -> str:
    """Convert a configuration identifier into a safe path component."""

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    cleaned = cleaned.strip("._")
    if not cleaned:
        raise ValueError("A source or company identifier cannot be blank.")
    return cleaned


def is_http_url(value: str) -> bool:
    """Return whether a value is an absolute HTTP(S) URL."""

    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def read_sources(path: Path) -> list[dict[str, str]]:
    """Load and validate the source registry."""

    if not path.exists():
        raise FileNotFoundError(f"Source registry not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - fieldnames
        if missing:
            raise ValueError(
                f"{path.name} is missing columns: {sorted(missing)}"
            )
        rows = list(reader)

    if not rows:
        raise ValueError(f"{path.name} contains no source records.")

    source_ids: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        source_id = row.get("source_id", "").strip()
        company_id = row.get("company_id", "").strip()
        source_type = row.get("source_type", "").strip().lower()
        source_url = row.get("source_url", "").strip()

        if not source_id or not company_id:
            raise ValueError(
                f"{path.name} row {row_number}: blank source_id or company_id."
            )
        if source_id in source_ids:
            raise ValueError(
                f"{path.name} row {row_number}: duplicate source_id {source_id!r}."
            )
        if source_type not in ALLOWED_SOURCE_TYPES:
            raise ValueError(
                f"{path.name} row {row_number}: unsupported source_type "
                f"{source_type!r}."
            )
        if not is_http_url(source_url):
            raise ValueError(
                f"{path.name} row {row_number}: invalid source_url."
            )
        source_ids.add(source_id)

    return rows


def build_session() -> requests.Session:
    """Create an HTTP session with conservative retry behaviour."""

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; "
                "InsuranceProfitabilityResearch/2025; public-data-study)"
            ),
            "Accept": (
                "text/html,application/pdf,text/csv,"
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
                "*/*;q=0.8"
            ),
        }
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def content_matches_type(source_type: str, content_type: str) -> bool:
    """Perform a lightweight check that the response resembles its declared type."""

    normalized = content_type.lower()
    if source_type == "html":
        return "html" in normalized
    if source_type == "pdf":
        return "pdf" in normalized or not normalized
    if source_type == "csv":
        return "csv" in normalized or "text/plain" in normalized
    if source_type == "xlsx":
        return (
            "spreadsheet" in normalized
            or "excel" in normalized
            or "octet-stream" in normalized
        )
    return False


def write_manifest(rows: list[dict[str, object]], path: Path) -> None:
    """Write a download audit trail."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def download_one(
    session: requests.Session,
    source: dict[str, str],
    output_dir: Path,
    timeout: int,
    overwrite: bool,
) -> dict[str, object]:
    """Download one configured source and return its manifest record."""

    source_id = source["source_id"].strip()
    company_id = source["company_id"].strip()
    source_type = source["source_type"].strip().lower()
    configured_url = source["source_url"].strip()

    destination = (
        output_dir
        / safe_path_part(company_id)
        / f"{safe_path_part(source_id)}{EXTENSION_BY_TYPE[source_type]}"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)

    base_record: dict[str, object] = {
        "source_id": source_id,
        "company_id": company_id,
        "source_title": source.get("source_title", "").strip(),
        "configured_url": configured_url,
        "final_url": "",
        "source_type": source_type,
        "content_type": "",
        "http_status": "",
        "download_status": "",
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "local_path": destination.relative_to(REPO_ROOT).as_posix(),
        "file_size_bytes": "",
        "sha256": "",
        "error": "",
    }

    if destination.exists() and not overwrite:
        payload = destination.read_bytes()
        return {
            **base_record,
            "download_status": "skipped_existing",
            "file_size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    try:
        response = session.get(
            configured_url,
            timeout=(15, timeout),
            allow_redirects=True,
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").split(";")[0]
        if not content_matches_type(source_type, content_type):
            raise ValueError(
                f"Expected {source_type}, received Content-Type "
                f"{content_type or '(missing)'}."
            )

        payload = response.content
        if not payload:
            raise ValueError("The server returned an empty file.")

        destination.write_bytes(payload)
        return {
            **base_record,
            "final_url": response.url,
            "content_type": content_type,
            "http_status": response.status_code,
            "download_status": "downloaded",
            "file_size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    except Exception as exc:
        return {
            **base_record,
            "download_status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }


def fetch_sources(
    config_path: Path = DEFAULT_CONFIG,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    manifest_path: Path = DEFAULT_MANIFEST,
    timeout: int = 120,
    overwrite: bool = False,
) -> list[dict[str, object]]:
    """Download every source listed in the registry."""

    sources = read_sources(config_path)
    session = build_session()
    manifest_rows: list[dict[str, object]] = []

    for index, source in enumerate(sources, start=1):
        label = f"{source['company_id']} / {source['source_id']}"
        print(f"[{index}/{len(sources)}] Downloading {label} ...")
        record = download_one(
            session=session,
            source=source,
            output_dir=output_dir,
            timeout=timeout,
            overwrite=overwrite,
        )
        manifest_rows.append(record)
        print(f"    {record['download_status']}")
        if record["error"]:
            print(f"    {record['error']}")

    write_manifest(manifest_rows, manifest_path)
    return manifest_rows


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(
        description="Download public report sources configured in sources_2025.csv."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Download again even when a local file already exists.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the downloader and report a concise status summary."""

    args = parse_args()
    try:
        rows = fetch_sources(
            config_path=args.config,
            output_dir=args.output_dir,
            manifest_path=args.manifest,
            timeout=args.timeout,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    downloaded = sum(row["download_status"] == "downloaded" for row in rows)
    skipped = sum(row["download_status"] == "skipped_existing" for row in rows)
    failed = sum(row["download_status"] == "failed" for row in rows)

    print()
    print("Download summary")
    print(f"Downloaded: {downloaded}")
    print(f"Skipped existing: {skipped}")
    print(f"Failed: {failed}")
    print(f"Manifest: {args.manifest}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
