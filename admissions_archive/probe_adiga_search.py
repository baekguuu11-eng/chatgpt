from __future__ import annotations

import html
import json
import re
from pathlib import Path

import requests

BASE = "https://www.adiga.kr"
LIST_URL = f"{BASE}/uct/ces/archiveView.do?menuId=PCUCTCES1000"
AJAX_URL = f"{BASE}/uct/ces/archiveAjax.do"
TARGETS = [
    "2028학년도 대학입학전형시행계획(ㅂ~을).zip",
    "2028학년도 대학입학전형시행계획(이~ㅎ).zip",
]

session = requests.Session()
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 AdmissionsArchive/1.0",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": LIST_URL,
    }
)
session.get(LIST_URL, timeout=60).raise_for_status()

results = []
for target in TARGETS:
    payload = {
        "pagination.currentPage": "1",
        "pagination.cntPerPage": "50",
        "searchSyr": "2028",
        "searchKey": "searchTtlCn",
        "searchWord": target.replace(".zip", ""),
        "prtlBbsId": "",
    }
    response = session.post(AJAX_URL, data=payload, timeout=90)
    response.raise_for_status()
    text = response.text
    Path("output/logs").mkdir(parents=True, exist_ok=True)
    Path("output/logs", f"probe_{len(results)+1}.html").write_text(text, encoding="utf-8")
    found = []
    for match in re.finditer(r"fnDownloadAll\((\[.*?\])\);", text, re.S):
        try:
            attachments = json.loads(html.unescape(match.group(1)))
        except json.JSONDecodeError:
            continue
        for item in attachments:
            name = str(item.get("atchFileNm", ""))
            if "2028학년도 대학입학전형시행계획" in name:
                found.append(item)
    results.append({"target": target, "status": response.status_code, "bytes": len(response.content), "attachments": found})

Path("output/adiga_probe.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
