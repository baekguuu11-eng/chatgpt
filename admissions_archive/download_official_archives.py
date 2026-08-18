from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path("output")
RAW = ROOT / "raw_archives"
EXTRACTED = ROOT / "official_documents"
LOGS = ROOT / "logs"
for path in (RAW, EXTRACTED, LOGS):
    path.mkdir(parents=True, exist_ok=True)

ARCHIVES = [
    {
        "name": "2028_시행계획_가-광.zip",
        "file_id": "00000000000000256172",
        "file_sn": 1,
        "expected_size": 22495933,
    },
    {
        "name": "2028_시행계획_국-ㅁ.zip",
        "file_id": "00000000000000256175",
        "file_sn": 2,
        "expected_size": 25992498,
    },
    {
        "name": "2028_시행계획_ㅂ-을.zip",
        "file_id": "00000000000000256178",
        "file_sn": 3,
        "expected_size": None,
    },
    {
        "name": "2028_시행계획_이-ㅎ.zip",
        "file_id": "00000000000000256181",
        "file_sn": 4,
        "expected_size": None,
    },
]

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36 AdmissionsArchive/1.0",
        "Accept": "application/zip,application/octet-stream,*/*",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
        "Referer": "https://www.adiga.kr/uct/ces/archiveView.do?menuId=PCUCTCES1001",
    }
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(name: str) -> str:
    name = name.replace("\\", "/").lstrip("/")
    parts = []
    for part in name.split("/"):
        if not part or part in {".", ".."}:
            continue
        part = re.sub(r"[<>:\"|?*]", "_", part)
        parts.append(part)
    return "/".join(parts) or "unnamed"


def candidate_urls(file_id: str, file_sn: int) -> list[str]:
    query = f"fileId={file_id}&fileSn={file_sn}"
    return [
        f"https://www.adiga.kr/cmm/com/file/fileDown.do?{query}",
        f"https://adiga.kr/cmm/com/file/fileDown.do?{query}",
        f"https://m.adiga.kr/cmm/com/file/fileDown.do?{query}",
    ]


def download_archive(spec: dict) -> tuple[Path | None, dict]:
    errors: list[str] = []
    for url in candidate_urls(spec["file_id"], spec["file_sn"]):
        try:
            response = SESSION.get(url, timeout=180, allow_redirects=True)
            data = response.content
            ctype = response.headers.get("content-type", "")
            info = {
                "requested_url": url,
                "final_url": response.url,
                "status": response.status_code,
                "content_type": ctype,
                "bytes": len(data),
                "sha256": sha256_bytes(data),
            }
            if response.status_code != 200:
                errors.append(json.dumps(info, ensure_ascii=False))
                continue
            target = RAW / spec["name"]
            target.write_bytes(data)
            if not zipfile.is_zipfile(target):
                bad = LOGS / f"{spec['name']}.not_zip.bin"
                shutil.move(target, bad)
                info["error"] = "response is not a ZIP archive"
                errors.append(json.dumps(info, ensure_ascii=False))
                continue
            info["expected_size"] = spec.get("expected_size")
            info["size_matches_expected"] = (
                spec.get("expected_size") is None or len(data) == spec["expected_size"]
            )
            return target, info
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    return None, {"errors": errors}


def extract_archive(archive_path: Path, archive_name: str) -> list[dict]:
    rows: list[dict] = []
    archive_dir = EXTRACTED / archive_path.stem
    archive_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as zf:
        for index, member in enumerate(zf.infolist(), start=1):
            if member.is_dir():
                continue
            member_name = safe_name(member.filename)
            out = archive_dir / member_name
            out.parent.mkdir(parents=True, exist_ok=True)
            data = zf.read(member)
            out.write_bytes(data)
            rows.append(
                {
                    "archive": archive_name,
                    "member_index": index,
                    "member_name": member.filename,
                    "local_path": out.as_posix(),
                    "extension": out.suffix.lower(),
                    "bytes": len(data),
                    "sha256": sha256_bytes(data),
                    "zip_crc": f"{member.CRC:08x}",
                    "source_type": "대입정보포털 어디가 공식 2028 시행계획 묶음",
                }
            )
    return rows


def main() -> int:
    download_log: list[dict] = []
    members: list[dict] = []
    failures: list[dict] = []

    for spec in ARCHIVES:
        path, info = download_archive(spec)
        info["archive_name"] = spec["name"]
        info["file_id"] = spec["file_id"]
        info["file_sn"] = spec["file_sn"]
        download_log.append(info)
        if path is None:
            failures.append(info)
            continue
        members.extend(extract_archive(path, spec["name"]))

    with (ROOT / "archive_download_log.json").open("w", encoding="utf-8") as f:
        json.dump(download_log, f, ensure_ascii=False, indent=2)

    fieldnames = [
        "archive",
        "member_index",
        "member_name",
        "local_path",
        "extension",
        "bytes",
        "sha256",
        "zip_crc",
        "source_type",
    ]
    with (ROOT / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(members)

    unique_hashes = {row["sha256"] for row in members}
    summary = {
        "archives_attempted": len(ARCHIVES),
        "archives_downloaded": len(ARCHIVES) - len(failures),
        "extracted_files": len(members),
        "unique_content_files": len(unique_hashes),
        "failures": failures,
    }
    with (ROOT / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # This first pass is intentionally successful even below 300 so the next
    # collection stage can inspect the exact official archive count.
    return 0 if members else 1


if __name__ == "__main__":
    raise SystemExit(main())
