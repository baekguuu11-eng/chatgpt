from __future__ import annotations

import json
import re
from pathlib import Path

import requests

PAGE_URL = "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do?menuId=PCUVTINF2000&searchSyr=2027&unvCd=0000063"
AJAX_URL = "https://www.adiga.kr/uct/acd/ade/criteriaAndResultItemNewAjax.do"
OUT = Path("selection_code_probe")
OUT.mkdir(exist_ok=True)

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
})
page = s.get(PAGE_URL, timeout=60)
page.raise_for_status()
(OUT / "selection_page.html").write_bytes(page.content)

codes = ["", "10", "20", "30", "31", "32", "33", "40", "41", "42", "43", "50"]
rows = []
for code in codes:
    form = {
        "searchSyr": "2027",
        "unvCd": "0000063",
        "tsrdCmphSlcnArtclUpCd": code,
        "compUnvCd": "",
    }
    r = s.post(AJAX_URL, data=form, timeout=60, headers={
        "Referer": PAGE_URL,
        "X-Requested-With": "XMLHttpRequest",
    })
    text = r.text
    filename = f"code_{code or 'empty'}.html"
    (OUT / filename).write_text(text, encoding="utf-8")
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    rows.append({
        "code": code,
        "status": r.status_code,
        "bytes": len(r.content),
        "tables": len(re.findall(r"<table", text, re.I)),
        "result_blocks": text.count('tbAdmRes'),
        "contains_2026": "2026" in text,
        "contains_competition": "경쟁률" in text,
        "contains_70_cut": "70%" in text or "70％" in text,
        "snippet": cleaned[:500],
    })

(OUT / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(rows, ensure_ascii=False, indent=2))
