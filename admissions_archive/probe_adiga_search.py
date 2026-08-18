from __future__ import annotations

import html
import json
import re
from pathlib import Path

import requests

BASE = "https://www.adiga.kr"
LIST_URL = f"{BASE}/uct/ces/archiveView.do?menuId=PCUCTCES1000"
AJAX_URL = f"{BASE}/uct/ces/archiveAjax.do"

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
Path("output/logs").mkdir(parents=True, exist_ok=True)

seen: set[tuple[str, int]] = set()
attachments: list[dict] = []
pages: list[dict] = []
for page in range(1, 31):
    payload = {
        "pagination.currentPage": str(page),
        "pagination.cntPerPage": "50",
        "searchSyr": "2028",
        "searchKey": "searchTtlCn",
        "searchWord": "",
        "prtlBbsId": "",
    }
    response = session.post(AJAX_URL, data=payload, timeout=90)
    response.raise_for_status()
    text = response.text
    Path("output/logs", f"probe_page_{page:02d}.html").write_text(text, encoding="utf-8")
    found_on_page = 0
    for match in re.finditer(r"fnDownloadAll\((\[.*?\])\);", text, re.S):
        try:
            payload_items = json.loads(html.unescape(match.group(1)))
        except json.JSONDecodeError:
            continue
        for item in payload_items:
            name = str(item.get("atchFileNm", ""))
            if "2028학년도 대학입학전형시행계획" not in name or not name.lower().endswith(".zip"):
                continue
            key = (str(item.get("fileId", "")), int(item.get("fileSn", 0)))
            if key in seen:
                continue
            seen.add(key)
            attachments.append(item)
            found_on_page += 1
    pages.append({"page": page, "bytes": len(response.content), "found": found_on_page})
    # Empty/very small fragments after the useful range indicate the end.
    if page > 3 and len(response.content) < 1200 and found_on_page == 0:
        break

result = {"pages": pages, "attachments": attachments}
Path("output/adiga_probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
