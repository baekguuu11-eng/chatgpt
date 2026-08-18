from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path("output/official_university_results")
ROOT.mkdir(parents=True, exist_ok=True)
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36 AdmissionsArchive/1.0",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
})

DONGGUK = [
    (2026, "통합", "20260804102857MRDVXS.PDF"), (2026, "통합", "20260804102624XZUUVJ.HWP"),
    (2025, "통합", "20250616162245PAJ443.PDF"), (2025, "통합", "20250616162245P7KS83.HWP"),
    (2024, "정시", "20240501095746JHGHCW.PDF"), (2024, "정시", "20240501095746JEG7FW.HWP"),
    (2024, "수시", "202406071113123QQ9P2.PDF"), (2024, "수시", "20240607111312YY2PJ5.HWP"),
    (2023, "정시", "20230926173019EURR42.PDF"), (2023, "정시", "20230926173019EQSF82.HWP"),
    (2023, "수시", "20230516123458427BZL.PDF"), (2023, "수시", "20230516123459PHKRGW.HWP"),
    (2022, "정시", "20220602132837KUALH3.PDF"), (2022, "정시", "20220614150712M9FYMZ.HWP"),
    (2022, "수시", "202209161347546EKSPB.PDF"), (2022, "수시", "202209161347548XAQ59.HWP"),
    (2021, "정시", "20220425163905T7QM7M.PDF"), (2021, "정시", "20220425163905T4RBBM.HWP"),
    (2021, "수시", "20211220102206H5XZ24.PDF"), (2021, "수시", "20211220102206H2XP64.HWP"),
    (2020, "정시", "20200827163949P7WJZK.PDF"), (2020, "정시", "20200827163949RQMGFG.HWP"),
    (2020, "수시", "202005191720525XGFMS.PDF"), (2020, "수시", "20200519172052PHLNQ7.HWP"),
]

INU_LISTS = [
    ("수시", "https://admission.inu.ac.kr/submenu.do?menuurl=4428MQNdeF7ekIPFWbVCAg%3D%3D"),
    ("정시", "https://admission.inu.ac.kr/submenu.do?menuurl=7o6CZK4SE%2FZm%2Fkm5uoXMkQ%3D%3D"),
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', '_', value).strip() or "unnamed"


def valid_content(path: Path, data: bytes) -> bool:
    if len(data) < 100:
        return False
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return data.startswith(b"%PDF")
    if suffix == ".hwp":
        return data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")) or data.startswith(b"PK")
    if suffix in {".hwpx", ".xlsx", ".zip"}:
        return data.startswith(b"PK")
    return b"<html" not in data[:500].lower()


def save_file(university: str, year: int, category: str, url: str, filename: str) -> dict:
    response = SESSION.get(url, timeout=180, allow_redirects=True)
    response.raise_for_status()
    data = response.content
    folder = ROOT / university / str(year) / category
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / safe(filename)
    target.write_bytes(data)
    return {
        "university": university,
        "year": year,
        "category": category,
        "file_name": target.name,
        "local_path": target.as_posix(),
        "official_url": url,
        "bytes": len(data),
        "sha256": digest(data),
        "valid": valid_content(target, data),
    }


rows: list[dict] = []
failures: list[dict] = []

# Dongguk's official page exposes these static files under /upload/file/.
for year, category, token in DONGGUK:
    url = f"https://ipsi.dongguk.edu/upload/file/{token}"
    ext = Path(token).suffix.lower()
    filename = f"{year}_동국대학교_{category}_입시결과_{token}{ext if not token.lower().endswith(ext) else ''}"
    try:
        row = save_file("동국대학교", year, category, url, filename)
        rows.append(row)
        if not row["valid"]:
            failures.append({"url": url, "reason": "validation failed"})
    except Exception as exc:  # noqa: BLE001
        failures.append({"url": url, "reason": f"{type(exc).__name__}: {exc}"})

# Incheon University: discover all 2020-2026 result detail pages and attachments.
seen_details: set[str] = set()
seen_files: set[str] = set()
for category, list_url in INU_LISTS:
    for page_no in range(1, 8):
        separator = "&" if "?" in list_url else "?"
        page_url = f"{list_url}{separator}pageNo={page_no}"
        try:
            response = SESSION.get(page_url, timeout=90)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            failures.append({"url": page_url, "reason": f"list: {type(exc).__name__}: {exc}"})
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        detail_links = []
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            text = anchor.get_text(" ", strip=True)
            combined = f"{href} {text}"
            if "detail.do" not in href or not any(str(y) in combined for y in range(2020, 2027)):
                continue
            detail_links.append(urljoin(page_url, href))
        if not detail_links and page_no > 2:
            break
        for detail_url in detail_links:
            if detail_url in seen_details:
                continue
            seen_details.add(detail_url)
            try:
                detail = SESSION.get(detail_url, timeout=90)
                detail.raise_for_status()
                detail_soup = BeautifulSoup(detail.text, "html.parser")
                page_text = detail_soup.get_text(" ", strip=True)
                years = [y for y in range(2020, 2027) if f"{y}학년도" in page_text or str(y) in page_text[:600]]
                if not years:
                    continue
                year = max(years)
                if not any(k in page_text for k in ("입시결과", "전형결과", "입학전형 결과", "입학 결과")):
                    continue
                for anchor in detail_soup.find_all("a", href=True):
                    href = anchor.get("href", "")
                    label = anchor.get_text(" ", strip=True)
                    combined = f"{href} {label}"
                    if not re.search(r"\.(pdf|hwp|hwpx|xlsx?|zip)(?:$|[?&])", combined, re.I) and not any(k in href.lower() for k in ("download", "filedown", "attach")):
                        continue
                    file_url = urljoin(detail_url, href)
                    if file_url in seen_files:
                        continue
                    seen_files.add(file_url)
                    guessed = label or Path(file_url.split("?")[0]).name or f"{year}_{category}_attachment.bin"
                    guessed = safe(guessed)
                    if "." not in guessed:
                        match = re.search(r"[^/?&=]+\.(pdf|hwp|hwpx|xlsx?|zip)", combined, re.I)
                        guessed = match.group(0) if match else f"{year}_인천대학교_{category}_입시결과_{len(seen_files):03d}.bin"
                    row = save_file("인천대학교", year, category, file_url, guessed)
                    rows.append(row)
                    if not row["valid"]:
                        failures.append({"url": file_url, "reason": "validation failed"})
            except Exception as exc:  # noqa: BLE001
                failures.append({"url": detail_url, "reason": f"detail: {type(exc).__name__}: {exc}"})

fields = ["university", "year", "category", "file_name", "local_path", "official_url", "bytes", "sha256", "valid"]
with Path("output/university_result_manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

valid_rows = [r for r in rows if r["valid"]]
summary = {
    "downloaded": len(rows),
    "valid_files": len(valid_rows),
    "unique_valid_content": len({r["sha256"] for r in valid_rows}),
    "by_university": {
        university: sum(1 for r in valid_rows if r["university"] == university)
        for university in sorted({r["university"] for r in valid_rows})
    },
    "failures": failures,
}
Path("output/university_result_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
