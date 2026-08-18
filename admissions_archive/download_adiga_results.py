from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from pathlib import Path

import requests

BASE = "https://www.adiga.kr"
LIST_URL = f"{BASE}/uct/ces/archiveView.do?menuId=PCUCTCES1000"
AJAX_URL = f"{BASE}/uct/ces/archiveAjax.do"
OUT = Path("output/official_results")
OUT.mkdir(parents=True, exist_ok=True)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 AdmissionsArchive/1.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": LIST_URL,
})
session.get(LIST_URL, timeout=60).raise_for_status()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', '_', name).strip() or "unnamed"


def parse_attachments(text: str) -> list[dict]:
    found: list[dict] = []
    for match in re.finditer(r"fnDownloadAll\((\[.*?\])\);", text, re.S):
        try:
            items = json.loads(html.unescape(match.group(1)))
        except json.JSONDecodeError:
            continue
        found.extend(item for item in items if isinstance(item, dict))
    return found


# ADIGA commonly classifies the prior admission year's result report under the
# following portal year (e.g. 2025 admission results are labelled 2026).
queries: list[tuple[int, int, str]] = []
for admission_year in range(2020, 2027):
    portal_years = sorted({admission_year, admission_year + 1, 0})
    for portal_year in portal_years:
        for term in (
            f"{admission_year}학년도 대입 전형결과",
            f"{admission_year}학년도 대입전형 결과",
            f"{admission_year}학년도 전형결과",
            f"{admission_year}학년도 입시결과",
        ):
            queries.append((admission_year, portal_year, term))

candidates: dict[tuple[str, int], dict] = {}
query_log: list[dict] = []
for admission_year, portal_year, term in queries:
    payload = {
        "pagination.currentPage": "1",
        "pagination.cntPerPage": "100",
        "searchSyr": str(portal_year) if portal_year else "",
        "searchKey": "searchTtlCn",
        "searchWord": term,
        "prtlBbsId": "",
    }
    response = session.post(AJAX_URL, data=payload, timeout=90)
    response.raise_for_status()
    items = parse_attachments(response.text)
    accepted = 0
    for item in items:
        name = str(item.get("atchFileNm", ""))
        if str(admission_year) not in name:
            continue
        if not any(token in name for token in ("전형결과", "전형 결과", "입시결과", "입학결과")):
            continue
        try:
            key = (str(item["fileId"]), int(item["fileSn"]))
        except (KeyError, TypeError, ValueError):
            continue
        enriched = dict(item)
        enriched["admission_year"] = admission_year
        enriched["portal_year"] = portal_year
        enriched["query_term"] = term
        candidates[key] = enriched
        accepted += 1
    query_log.append({
        "admission_year": admission_year,
        "portal_year": portal_year,
        "term": term,
        "response_bytes": len(response.content),
        "attachments_seen": len(items),
        "accepted": accepted,
    })

rows: list[dict] = []
failures: list[dict] = []
for (file_id, file_sn), item in sorted(candidates.items(), key=lambda kv: (kv[1]["admission_year"], kv[1].get("atchFileNm", ""))):
    url = f"{BASE}/cmm/com/file/fileDown.do?fileId={file_id}&fileSn={file_sn}"
    try:
        response = session.get(url, timeout=180, allow_redirects=True)
        response.raise_for_status()
        data = response.content
        expected = int(item.get("fileSz") or 0)
        name = safe_name(str(item.get("atchFileNm") or f"{file_id}_{file_sn}.bin"))
        year_dir = OUT / str(item["admission_year"])
        year_dir.mkdir(parents=True, exist_ok=True)
        target = year_dir / name
        target.write_bytes(data)
        valid = len(data) > 0 and (expected == 0 or len(data) == expected)
        if target.suffix.lower() == ".pdf":
            valid = valid and data.startswith(b"%PDF")
        rows.append({
            "admission_year": item["admission_year"],
            "portal_year": item["portal_year"],
            "file_name": name,
            "local_path": target.as_posix(),
            "official_url": url,
            "file_id": file_id,
            "file_sn": file_sn,
            "bytes": len(data),
            "expected_bytes": expected,
            "sha256": sha256(data),
            "valid": valid,
            "source_type": "대입정보포털 어디가 공식 대입 전형결과",
        })
        if not valid:
            failures.append({"file_name": name, "reason": "validation failed", "url": url})
    except Exception as exc:  # noqa: BLE001
        failures.append({
            "file_name": item.get("atchFileNm"),
            "url": url,
            "reason": f"{type(exc).__name__}: {exc}",
        })

fields = [
    "admission_year", "portal_year", "file_name", "local_path", "official_url",
    "file_id", "file_sn", "bytes", "expected_bytes", "sha256", "valid", "source_type",
]
with Path("output/result_manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

valid_rows = [row for row in rows if row["valid"]]
summary = {
    "queries": query_log,
    "candidates": len(candidates),
    "downloaded": len(rows),
    "valid_files": len(valid_rows),
    "unique_valid_content": len({row["sha256"] for row in valid_rows}),
    "by_year": {
        str(year): sum(1 for row in valid_rows if row["admission_year"] == year)
        for year in range(2020, 2027)
    },
    "failures": failures,
}
Path("output/result_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "queries"}, ensure_ascii=False, indent=2))
