from __future__ import annotations

import json
import threading
from pathlib import Path

from bs4 import BeautifulSoup

import collect_adiga_total_500 as base

_write_lock = threading.Lock()


def safe_save_document(data: bytes, suffix: str, metadata: dict) -> tuple[str, str]:
    digest = base.sha256(data)
    target = base.DOCS / f"{digest}{suffix}"
    meta = base.DOCS / f"{digest}.json"
    with _write_lock:
        if not target.exists():
            target.write_bytes(data)
        if not meta.exists():
            meta.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return digest, target.relative_to(base.FINAL).as_posix()


def robust_result_response_valid(text: str) -> tuple[bool, int, str]:
    if not text or len(text) < 250:
        return False, 0, ""
    soup = BeautifulSoup(text, "html.parser")
    plain = base.clean_text(soup.get_text(" ", strip=True))
    tables = soup.find_all("table")
    row_count = sum(len(table.find_all("tr")) for table in tables)
    result_blocks = len(soup.select(".tbAdmRes")) + text.count('class="tbAdmRes"')
    metric_count = sum(
        marker in plain
        for marker in ("경쟁률", "70%", "50%", "충원", "최종등록", "환산점수", "백분위", "모집인원")
    )
    heading = any(marker in plain for marker in ("전형 결과", "전형결과", "입시 결과", "입시결과", "선발 결과"))
    valid = (
        (result_blocks > 0 and row_count >= 2 and metric_count >= 2)
        or (row_count >= 5 and metric_count >= 3 and heading)
    )
    return valid, row_count, plain[:1200]


base.save_document = safe_save_document
base.result_response_valid = robust_result_response_valid

if __name__ == "__main__":
    raise SystemExit(base.main())
