from __future__ import annotations

import html
import json
import re
from pathlib import Path

import requests

BASE = "https://www.adiga.kr"
LIST_URL = f"{BASE}/uct/ces/archiveView.do?menuId=PCUCTCES1000"
AJAX_URL = f"{BASE}/uct/ces/archiveAjax.do"
YEARS = range(2020, 2027)
TERMS = [
    "입시결과",
    "입학결과",
    "전형결과",
    "대입전형 결과",
    "평가기준 및 결과",
    "전년도 결과",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 AdmissionsArchive/1.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": LIST_URL,
})
session.get(LIST_URL, timeout=60).raise_for_status()
Path("output/result_probe").mkdir(parents=True, exist_ok=True)

seen: set[tuple[str, int]] = set()
found: list[dict] = []
queries: list[dict] = []
for year in YEARS:
    for term in TERMS:
        payload = {
            "pagination.currentPage": "1",
            "pagination.cntPerPage": "100",
            "searchSyr": str(year),
            "searchKey": "searchTtlCn",
            "searchWord": term,
            "prtlBbsId": "",
        }
        response = session.post(AJAX_URL, data=payload, timeout=90)
        response.raise_for_status()
        text = response.text
        slug = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", term)
        Path("output/result_probe", f"{year}_{slug}.html").write_text(text, encoding="utf-8")
        local_count = 0
        for match in re.finditer(r"fnDownloadAll\((\[.*?\])\);", text, re.S):
            try:
                items = json.loads(html.unescape(match.group(1)))
            except json.JSONDecodeError:
                continue
            for item in items:
                name = str(item.get("atchFileNm", ""))
                title_context = text[max(0, match.start()-1200):match.end()+300]
                combined = f"{name} {title_context}"
                if str(year) not in combined:
                    continue
                if not any(k in combined for k in ("입시결과", "입학결과", "전형결과", "평가기준", "전년도 결과")):
                    continue
                try:
                    key = (str(item["fileId"]), int(item["fileSn"]))
                except (KeyError, TypeError, ValueError):
                    continue
                if key in seen:
                    continue
                seen.add(key)
                row = dict(item)
                row["query_year"] = year
                row["query_term"] = term
                row["context_excerpt"] = re.sub(r"\s+", " ", title_context)[:1000]
                found.append(row)
                local_count += 1
        queries.append({"year": year, "term": term, "bytes": len(response.content), "found": local_count})

result = {"queries": queries, "attachments": found, "count": len(found)}
Path("output/adiga_result_probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"count": len(found), "attachments": found[:30]}, ensure_ascii=False, indent=2))
