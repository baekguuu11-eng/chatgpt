from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup

BASE = "https://admission.ssu.ac.kr"
OUT = Path("output/official_university_results/숭실대학교")
OUT.mkdir(parents=True, exist_ok=True)
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36 AdmissionsArchive/1.0",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
})

# Official result/statistics detail pages. These include integrated annual
# statistics and cumulative result reports for student-record, essay, and
# regular admissions.
PAGES = [
    "https://admission.ssu.ac.kr/board/statistics_view.asp?flag=1&number=241&page=1&page_no=1_2_6",
    "https://admission.ssu.ac.kr/board/statistics_view.asp?flag=1&number=238&page=1&page_no=1_2_6",
    "https://admission.ssu.ac.kr/board/statistics_view.asp?flag=1&number=232&page=1&page_no=1_2_6",
    "https://admission.ssu.ac.kr/board/statistics_view.asp?flag=1&number=226&page=1&page_no=1_2_6",
    "https://admission.ssu.ac.kr/board/statistics_view.asp?flag=1&number=191&page=1&page_no=1_2_6",
    "https://admission.ssu.ac.kr/board/statistics_view.asp?flag=2&number=231&page=1&page_no=1_2_4",
    "https://admission.ssu.ac.kr/board/statistics_view.asp?flag=2&number=230&page=1&page_no=1_2_4",
    "https://admission.ssu.ac.kr/board/statistics_view.asp?flag=2&number=229&page=1&page_no=1_2_4",
    "https://admission.ssu.ac.kr/board/statistics_view.asp?flag=3&number=231&page=1&page_no=1_3_4",
    "https://admission.ssu.ac.kr/board/statistics_view.asp?flag=3&number=230&page=1&page_no=1_3_4",
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', '_', unquote(name)).strip() or "unnamed"


def infer_year(text: str) -> int:
    years = [int(x) for x in re.findall(r"20(?:20|21|22|23|24|25|26)학년도", text)]
    return max(years) if years else 0


def valid(path: Path, data: bytes) -> bool:
    if len(data) < 100:
        return False
    if path.suffix.lower() == ".pdf":
        return data.startswith(b"%PDF")
    if path.suffix.lower() == ".hwp":
        return data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")) or data.startswith(b"PK")
    return b"<html" not in data[:500].lower()


rows = []
failures = []
seen_urls = set()
for page_url in PAGES:
    try:
        response = SESSION.get(page_url, timeout=90)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser", from_encoding="euc-kr")
        page_text = soup.get_text(" ", strip=True)
        year = infer_year(page_text)
        candidates = []
        for a in soup.find_all("a"):
            href = a.get("href") or ""
            onclick = a.get("onclick") or ""
            label = a.get_text(" ", strip=True)
            blob = f"{href} {onclick} {label}"
            # Direct links and JS download calls.
            for match in re.findall(r"(?:https?://[^'\"\s)]+|/[^'\"\s)]+)", blob):
                if any(token in match.lower() for token in ("download", "filedown", ".pdf", ".hwp", ".hwpx", ".xlsx", ".zip")):
                    candidates.append((match, label))
            # Quoted arguments often contain the actual attachment path.
            for match in re.findall(r"['\"]([^'\"]+\.(?:pdf|hwp|hwpx|xlsx?|zip)(?:\?[^'\"]*)?)['\"]", blob, re.I):
                candidates.append((match, label))
        # Some pages embed attachment URLs in scripts, outside anchors.
        html_text = response.text
        for match in re.findall(r"(?:https?://[^'\"\s]+|/[^'\"\s]+)\.(?:pdf|hwp|hwpx|xlsx?|zip)(?:\?[^'\"\s]*)?", html_text, re.I):
            candidates.append((match, ""))

        for raw_url, label in candidates:
            file_url = urljoin(page_url, raw_url.replace("&amp;", "&"))
            if file_url in seen_urls:
                continue
            seen_urls.add(file_url)
            try:
                file_response = SESSION.get(file_url, timeout=180, allow_redirects=True, headers={"Referer": page_url})
                file_response.raise_for_status()
                data = file_response.content
                disp = file_response.headers.get("content-disposition", "")
                filename = ""
                m = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disp, re.I)
                if m:
                    filename = safe(m.group(1))
                if not filename:
                    filename = safe(label) if re.search(r"\.(pdf|hwp|hwpx|xlsx?|zip)$", label, re.I) else safe(Path(file_url.split("?")[0]).name)
                if not re.search(r"\.(pdf|hwp|hwpx|xlsx?|zip)$", filename, re.I):
                    ctype = file_response.headers.get("content-type", "").lower()
                    ext = ".pdf" if "pdf" in ctype else ".hwp" if "hwp" in ctype else ".bin"
                    filename = f"{year or 'unknown'}_숭실대학교_입시결과_{len(rows)+1:03d}{ext}"
                folder = OUT / str(year or "연도확인필요")
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / filename
                target.write_bytes(data)
                ok = valid(target, data)
                rows.append({
                    "university": "숭실대학교", "year": year, "source_page": page_url,
                    "file_name": filename, "local_path": target.as_posix(), "official_url": file_url,
                    "bytes": len(data), "sha256": sha(data), "valid": ok,
                })
                if not ok:
                    failures.append({"url": file_url, "reason": "validation failed"})
            except Exception as exc:  # noqa: BLE001
                failures.append({"url": file_url, "reason": f"file: {type(exc).__name__}: {exc}"})
    except Exception as exc:  # noqa: BLE001
        failures.append({"url": page_url, "reason": f"page: {type(exc).__name__}: {exc}"})

# Deduplicate manifest by hash; files remain preserved with their source names.
valid_rows = [r for r in rows if r["valid"]]
fields = ["university", "year", "source_page", "file_name", "local_path", "official_url", "bytes", "sha256", "valid"]
with Path("output/soongsil_manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader(); writer.writerows(rows)
summary = {
    "downloaded": len(rows),
    "valid_files": len(valid_rows),
    "unique_valid_content": len({r["sha256"] for r in valid_rows}),
    "failures": failures,
}
Path("output/soongsil_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
