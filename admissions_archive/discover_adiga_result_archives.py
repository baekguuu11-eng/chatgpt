from __future__ import annotations

import html
import json
import re
from pathlib import Path

import requests

BASE = "https://www.adiga.kr"
LIST_URL = f"{BASE}/uct/ces/archiveView.do?menuId=PCUCTCES1000"
AJAX_URL = f"{BASE}/uct/ces/archiveAjax.do"
OUT = Path("adiga_discovery")
OUT.mkdir(parents=True, exist_ok=True)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36 AdmissionsArchive/2.0",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": LIST_URL,
})
session.get(LIST_URL, timeout=60).raise_for_status()

RESULT_RE = re.compile(r"(?:대입|입학|입시)?\s*(?:전형)?\s*(?:결과|결과자료|결과 자료|통계|성적)")
YEAR_RE = re.compile(r"20(?:20|21|22|23|24|25|26)\s*학년도")

seen: set[tuple[str, int]] = set()
all_items: list[dict] = []
query_log: list[dict] = []

for search_year in [0, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027]:
    consecutive_empty = 0
    for page in range(1, 81):
        payload = {
            "pagination.currentPage": str(page),
            "pagination.cntPerPage": "100",
            "searchSyr": str(search_year) if search_year else "",
            "searchKey": "searchTtlCn",
            "searchWord": "",
            "prtlBbsId": "",
        }
        response = session.post(AJAX_URL, data=payload, timeout=90)
        response.raise_for_status()
        text = response.text
        found = 0
        matches = list(re.finditer(r"fnDownloadAll\((\[.*?\])\);", text, re.S))
        for match in matches:
            try:
                items = json.loads(html.unescape(match.group(1)))
            except json.JSONDecodeError:
                continue
            context = re.sub(r"<[^>]+>", " ", text[max(0, match.start()-1400):match.end()+500])
            context = re.sub(r"\s+", " ", html.unescape(context)).strip()
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    key = (str(item.get("fileId", "")), int(item.get("fileSn", 0)))
                except (TypeError, ValueError):
                    continue
                if not key[0] or key in seen:
                    continue
                seen.add(key)
                enriched = dict(item)
                enriched["search_year"] = search_year
                enriched["page"] = page
                enriched["context"] = context[:1800]
                name = str(item.get("atchFileNm", ""))
                combined = f"{name} {context}"
                enriched["candidate_result_archive"] = bool(YEAR_RE.search(combined) and RESULT_RE.search(combined))
                all_items.append(enriched)
                found += 1
        query_log.append({
            "search_year": search_year,
            "page": page,
            "bytes": len(response.content),
            "download_groups": len(matches),
            "new_attachments": found,
        })
        if not matches or len(response.content) < 1200:
            consecutive_empty += 1
        else:
            consecutive_empty = 0
        if page >= 3 and consecutive_empty >= 2:
            break

candidates = [x for x in all_items if x.get("candidate_result_archive")]
result = {
    "total_unique_attachments": len(all_items),
    "candidate_result_attachments": len(candidates),
    "candidates": candidates,
    "all_attachments": all_items,
    "query_log": query_log,
}
(OUT / "adiga_all_attachment_discovery.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps({
    "total_unique_attachments": len(all_items),
    "candidate_result_attachments": len(candidates),
    "candidate_names": [x.get("atchFileNm") for x in candidates],
}, ensure_ascii=False, indent=2))
