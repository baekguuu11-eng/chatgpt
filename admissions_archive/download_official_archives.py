from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import shutil
import zipfile
from pathlib import Path

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
        "page_url": "https://www.adiga.kr/uct/ces/archiveView.do?menuId=PCUCTCES1000&prtlBbsId=15938",
        "keyword": "2028학년도 대학입학전형시행계획(ㅂ~을).zip",
    },
    {
        "name": "2028_시행계획_이-ㅎ.zip",
        "page_url": "https://www.adiga.kr/uct/ces/archiveView.do?menuId=PCUCTCES1000&prtlBbsId=13556",
        "keyword": "2028학년도 대학입학전형시행계획(이~ㅎ).zip",
    },
]

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36 AdmissionsArchive/1.0",
        "Accept": "text/html,application/zip,application/octet-stream,*/*",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
        "Referer": "https://www.adiga.kr/uct/ces/archiveView.do?menuId=PCUCTCES1000",
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
        parts.append(re.sub(r"[<>:\"|?*]", "_", part))
    return "/".join(parts) or "unnamed"


def candidate_urls(file_id: str, file_sn: int) -> list[str]:
    query = f"fileId={file_id}&fileSn={file_sn}"
    return [
        f"https://www.adiga.kr/cmm/com/file/fileDown.do?{query}",
        f"https://adiga.kr/cmm/com/file/fileDown.do?{query}",
        f"https://m.adiga.kr/cmm/com/file/fileDown.do?{query}",
    ]


def discover_attachment(spec: dict) -> dict:
    if spec.get("file_id"):
        return dict(spec)
    response = SESSION.get(spec["page_url"], timeout=90)
    response.raise_for_status()
    text = html.unescape(response.text).replace("\\/", "/").replace("\\u0026", "&")
    (LOGS / f"{Path(spec['name']).stem}.html").write_text(text, encoding="utf-8")

    # Search each JSON-like attachment object and select the exact target ZIP.
    objects = re.findall(r"\{[^{}]{0,5000}\}", text, flags=re.S)
    for obj in objects:
        if spec["keyword"] not in obj and spec["name"].replace("2028_시행계획_", "2028학년도 대학입학전형시행계획(").replace(".zip", ").zip") not in obj:
            continue
        file_id = re.search(r'["\']?fileId["\']?\s*:\s*["\']([^"\']+)', obj)
        file_sn = re.search(r'["\']?fileSn["\']?\s*:\s*["\']?(\d+)', obj)
        file_size = re.search(r'["\']?fileSz["\']?\s*:\s*["\']?(\d+)', obj)
        file_name = re.search(r'["\']?(?:atchFileNm|fileName)["\']?\s*:\s*["\']([^"\']+)', obj)
        if file_id and file_sn:
            found = dict(spec)
            found["file_id"] = file_id.group(1)
            found["file_sn"] = int(file_sn.group(1))
            found["expected_size"] = int(file_size.group(1)) if file_size else None
            found["official_file_name"] = file_name.group(1) if file_name else spec["keyword"]
            return found

    # Fallback: locate the target filename and search nearby metadata.
    pos = text.find(spec["keyword"])
    if pos >= 0:
        nearby = text[max(0, pos - 4000) : pos + 4000]
        file_id = re.search(r'fileId[^0-9]*(\d{15,})', nearby)
        file_sn = re.search(r'fileSn[^0-9]*(\d+)', nearby)
        if file_id and file_sn:
            found = dict(spec)
            found["file_id"] = file_id.group(1)
            found["file_sn"] = int(file_sn.group(1))
            found["expected_size"] = None
            return found
    raise RuntimeError(f"Could not discover attachment metadata for {spec['keyword']}")


def download_archive(spec: dict) -> tuple[Path | None, dict]:
    errors: list[str] = []
    try:
        resolved = discover_attachment(spec)
    except Exception as exc:  # noqa: BLE001
        return None, {"errors": [f"discovery: {type(exc).__name__}: {exc}"]}

    for url in candidate_urls(resolved["file_id"], resolved["file_sn"]):
        try:
            response = SESSION.get(url, timeout=180, allow_redirects=True)
            data = response.content
            info = {
                "requested_url": url,
                "final_url": response.url,
                "status": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "bytes": len(data),
                "sha256": sha256_bytes(data),
                "resolved_file_id": resolved["file_id"],
                "resolved_file_sn": resolved["file_sn"],
            }
            if response.status_code != 200:
                errors.append(json.dumps(info, ensure_ascii=False))
                continue
            target = RAW / resolved["name"]
            target.write_bytes(data)
            if not zipfile.is_zipfile(target):
                bad = LOGS / f"{resolved['name']}.not_zip.bin"
                shutil.move(target, bad)
                info["error"] = "response is not a ZIP archive"
                errors.append(json.dumps(info, ensure_ascii=False))
                continue
            expected = resolved.get("expected_size")
            info["expected_size"] = expected
            info["size_matches_expected"] = expected is None or len(data) == expected
            return target, info
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    return None, {"errors": errors, "resolved": resolved}


def extract_archive(archive_path: Path, archive_name: str) -> list[dict]:
    rows: list[dict] = []
    archive_dir = EXTRACTED / archive_path.stem
    archive_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as zf:
        for index, member in enumerate(zf.infolist(), start=1):
            if member.is_dir():
                continue
            out = archive_dir / safe_name(member.filename)
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
        info["page_url"] = spec.get("page_url", "")
        download_log.append(info)
        if path is None:
            failures.append(info)
            continue
        members.extend(extract_archive(path, spec["name"]))

    (ROOT / "archive_download_log.json").write_text(
        json.dumps(download_log, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fieldnames = [
        "archive", "member_index", "member_name", "local_path", "extension",
        "bytes", "sha256", "zip_crc", "source_type",
    ]
    with (ROOT / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(members)

    summary = {
        "archives_attempted": len(ARCHIVES),
        "archives_downloaded": len(ARCHIVES) - len(failures),
        "extracted_files": len(members),
        "unique_content_files": len({row["sha256"] for row in members}),
        "failures": failures,
    }
    (ROOT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if members else 1


if __name__ == "__main__":
    raise SystemExit(main())
