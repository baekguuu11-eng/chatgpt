from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

OUT = Path("additional_200_output")
CACHE = OUT / "_cache"
FINAL = OUT / "additional_200_slots"
DOCS = FINAL / "documents"
POINTERS = FINAL / "slots"
for path in (CACHE, DOCS, POINTERS):
    path.mkdir(parents=True, exist_ok=True)

YEARS = tuple(range(2020, 2027))
RESULT_TERMS = (
    "입시결과", "입시 결과", "전형결과", "전형 결과", "입학전형 결과",
    "입학전형결과", "선발결과", "선발 결과", "최종등록자", "등록자 성적",
    "합격자 성적", "입시통계", "입시 통계", "전형통계", "전형 통계",
    "입학통계", "입학 통계", "성적 및 충원", "성적·충원", "입학성적",
)
EXCLUDE_TERMS = (
    "편입", "재외국민", "외국인", "대학원", "약학대학 편입", "계약학과 편입",
)
ATTACHMENT_EXTS = ("pdf", "hwp", "hwpx", "xls", "xlsx", "csv", "zip", "ppt", "pptx", "doc", "docx")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36 AdmissionsArchive/2.0",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
})


@dataclass(frozen=True)
class Seed:
    university: str
    domain_suffix: str
    urls: tuple[str, ...]
    max_pages: int = 28


SEEDS: tuple[Seed, ...] = (
    Seed("세종대학교", "sejong.ac.kr", (
        "https://ipsi.sejong.ac.kr/sub_page/sub5/0110_list.asp?B_CATEGORY=0&B_CODE=BOARD_1464103629&tab1=5",
    )),
    Seed("중앙대학교", "cau.ac.kr", (
        "https://admission.cau.ac.kr/submenu.do?boardid=3&categoryid=11&menuurl=%2Bwb2%2F2YpjUGJjmg2NfyS6Q%3D%3D&pageNo=1",
    )),
    Seed("경희대학교", "khu.ac.kr", (
        "https://iphak.khu.ac.kr/submenu.do?board_seq=2235&categoryid=37&menuurl=CQ%2BtdVujMr8ZrNNooONqJw%3D%3D",
    )),
    Seed("가천대학교", "gachon.ac.kr", (
        "https://admission.gachon.ac.kr/admission/html/rolling/result.asp",
        "https://admission.gachon.ac.kr/admission/html/regular/result.asp",
    )),
    Seed("아주대학교", "ajou.ac.kr", (
        "https://www.iajou.ac.kr/rate/?m_type=SUSI",
        "https://www.iajou.ac.kr/rate/?m_type=JEONGSI",
    )),
    Seed("숭실대학교", "ssu.ac.kr", (
        "https://admission.ssu.ac.kr/board/statistics_list.asp?flag=&keyword=&page=&page_no=1_2_5&srchoption=",
        "https://admission.ssu.ac.kr/board/statistics_list.asp?flag=1&keyword=&page=1&page_no=1_2_6&srchoption=",
    )),
    Seed("한국공학대학교", "tukorea.ac.kr", (
        "https://iphak.tukorea.ac.kr/susi/result.htm",
        "https://iphak.tukorea.ac.kr/jungsi/result.htm",
    )),
    Seed("강원대학교", "kangwon.ac.kr", (
        "https://admission.kangwon.ac.kr/admission/selectBbsNttList.do?bbsNo=376&integrDeptCode=&key=2419&searchCtgry=%ED%95%99%EB%B6%80%EC%9E%85%EC%8B%9C",
    )),
    Seed("충북대학교", "cbnu.ac.kr", (
        "https://ipsi.cbnu.ac.kr/kor/bbs/BBSMSTR_000000000053/lst.do",
    )),
    Seed("부산대학교", "pusan.ac.kr", (
        "https://go.pusan.ac.kr/college_2016/pages/index.asp?b=B_1_3&ct=1&p=7",
    )),
    Seed("제주대학교", "jejunu.ac.kr", (
        "https://ibsi.jejunu.ac.kr/10000048?categorycode=57&mode=list",
        "https://ibsi.jejunu.ac.kr/10000048?bbs_seq=45701&mode=view",
    )),
    Seed("국립공주대학교", "kongju.ac.kr", (
        "https://ipsi.kongju.ac.kr/kor/article/ATCL6131e0442/15963?pageIndex=1",
        "https://ipsi.kongju.ac.kr/kor/article/ATCL6131e0442/list?pageIndex=1",
    )),
    Seed("국립한국교통대학교", "ut.ac.kr", (
        "https://www.ut.ac.kr/cop/bbs/BBSMSTR_000000000663/selectBoardList.do?mno=sub01_03",
    )),
    Seed("국립한밭대학교", "hanbat.ac.kr", (
        "https://fund.hanbat.ac.kr/admission/index.do",
    )),
    Seed("국립금오공과대학교", "kumoh.ac.kr", (
        "https://iphak.kumoh.ac.kr/ipsi/sub010203.do",
        "https://iphak.kumoh.ac.kr/ipsi/sub020203.do",
    )),
    Seed("서울대학교", "snu.ac.kr", (
        "https://admission.snu.ac.kr/materials/stats/result",
        "https://admission.snu.ac.kr/materials/downloads/press",
    )),
    Seed("연세대학교", "yonsei.ac.kr", (
        "https://admission.yonsei.ac.kr/seoul/admission/html/counsel/data.asp?s_type=TYPE0",
    )),
    Seed("인천대학교", "inu.ac.kr", (
        "https://admission.inu.ac.kr/submenu.do?categoryid=0&menuurl=4428MQNdeF7ekIPFWbVCAg%3D%3D",
    )),
    Seed("서울시립대학교", "uos.ac.kr", (
        "https://admission.uos.ac.kr/admissionNew/main.do",
    )),
    Seed("홍익대학교 서울캠퍼스", "hongik.ac.kr", (
        "https://www.hongik.ac.kr/kr/admission/entrance-point.do?article.offset=0&mode=list",
    )),
    Seed("서강대학교", "sogang.ac.kr", (
        "https://admission3.sogang.ac.kr/enter/html/counsel/result.asp",
    )),
    Seed("건국대학교 글로컬캠퍼스", "kku.ac.kr", (
        "https://enter.kku.ac.kr/rate/index.php?f=&m_type=&nPage=1&s=",
    )),
    Seed("동아대학교", "donga.ac.kr", (
        "https://ent.donga.ac.kr/admission/html/rolling/result.asp",
        "https://ent.donga.ac.kr/admission/html/regular/result.asp",
    )),
    Seed("영남대학교", "yu.ac.kr", (
        "https://enter.yu.ac.kr/page/board/doumi_data.htm?ctg_cd=susi",
        "https://enter.yu.ac.kr/page/board/doumi_data.htm?ctg_cd=jungsi",
    )),
    Seed("인하대학교", "inha.ac.kr", (
        "https://admission.inha.ac.kr/",
    )),
    Seed("단국대학교 죽전캠퍼스", "dankook.ac.kr", (
        "https://ipsi.dankook.ac.kr/",
    )),
    Seed("한국항공대학교", "kau.ac.kr", (
        "https://ibhak.kau.ac.kr/",
    )),
    Seed("성균관대학교", "skku.edu", (
        "https://admission.skku.edu/",
    )),
    Seed("건국대학교 서울캠퍼스", "konkuk.ac.kr", (
        "https://enter.konkuk.ac.kr/",
    )),
    Seed("국립부경대학교", "pknu.ac.kr", (
        "https://iphak.pknu.ac.kr/",
    )),
    Seed("국립창원대학교", "changwon.ac.kr", (
        "https://ipsi.changwon.ac.kr/",
    )),
    Seed("국립한국해양대학교", "kmou.ac.kr", (
        "https://www.kmou.ac.kr/admission/main.do",
    )),
    Seed("전남대학교", "jnu.ac.kr", (
        "https://admission.jnu.ac.kr/",
    )),
    Seed("전북대학교", "jbnu.ac.kr", (
        "https://enter.jbnu.ac.kr/",
    )),
    Seed("충남대학교", "cnu.ac.kr", (
        "https://ipsi.cnu.ac.kr/",
    )),
    Seed("경상국립대학교", "gnu.ac.kr", (
        "https://www.gnu.ac.kr/new/na/ntt/selectNttList.do?mi=5114&bbsId=1954",
        "https://new.gnu.ac.kr/",
    )),
    Seed("국립군산대학교", "kunsan.ac.kr", (
        "https://www.kunsan.ac.kr/iphak/index.kunsan",
    )),
    Seed("국립목포대학교", "mokpo.ac.kr", (
        "https://ipsi.mokpo.ac.kr/",
    )),
    Seed("국립순천대학교", "scnu.ac.kr", (
        "https://www.scnu.ac.kr/iphak/main.do",
    )),
    Seed("한국기술교육대학교", "koreatech.ac.kr", (
        "https://ipsi.koreatech.ac.kr/",
    )),
    Seed("고려대학교 세종캠퍼스", "korea.ac.kr", (
        "https://oku.korea.ac.kr/sejong/",
    )),
    Seed("연세대학교 미래캠퍼스", "yonsei.ac.kr", (
        "https://admission.yonsei.ac.kr/mirae/",
    )),
    Seed("단국대학교 천안캠퍼스", "dankook.ac.kr", (
        "https://ipsi.dankook.ac.kr/",
    )),
    Seed("순천향대학교", "sch.ac.kr", (
        "https://ipsi.sch.ac.kr/",
    )),
    Seed("한림대학교", "hallym.ac.kr", (
        "https://admission.hallym.ac.kr/",
    )),
    Seed("울산대학교", "ulsan.ac.kr", (
        "https://iphak.ulsan.ac.kr/",
    )),
    Seed("계명대학교", "kmu.ac.kr", (
        "https://www.gokmu.ac.kr/",
    )),
    Seed("조선대학교", "chosun.ac.kr", (
        "https://ibhak.chosun.ac.kr/",
    )),
    Seed("원광대학교", "wku.ac.kr", (
        "https://ipsi.wku.ac.kr/",
    )),
    Seed("호서대학교", "hoseo.edu", (
        "https://ipsi.hoseo.ac.kr/",
    )),
    Seed("선문대학교", "sunmoon.ac.kr", (
        "https://lily.sunmoon.ac.kr/admission/",
    )),
)

# Slots already represented in the previous archive. 2028 is not collected in
# this job at all, so the 90 existing 2028 slots cannot overlap.
EXISTING_SLOTS: set[tuple[str, int]] = set()
for y in YEARS:
    EXISTING_SLOTS.add(("동국대학교 서울캠퍼스", y))
    EXISTING_SLOTS.add(("광운대학교", y))
for y in range(2022, 2027):
    EXISTING_SLOTS.add(("한양대학교 ERICA캠퍼스", y))
EXISTING_SLOTS.add(("국민대학교", 2026))


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def safe_name(value: str) -> str:
    value = normalize_space(value)
    value = re.sub(r"[<>:\"/\\|?*]+", "_", value)
    return value[:180].strip(" ._") or "unnamed"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def official_host(url: str, suffix: str) -> bool:
    host = (urlparse(url).hostname or "").lower().strip(".")
    suffix = suffix.lower().strip(".")
    return host == suffix or host.endswith("." + suffix)


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k.lower() not in {"utm_source", "utm_medium", "utm_campaign", "sessionid", "jsessionid"}]
    return urlunparse((parsed.scheme or "https", parsed.netloc.lower(), parsed.path, parsed.params,
                       urlencode(query, doseq=True), ""))


def extract_years(text: str) -> set[int]:
    text = normalize_space(text)
    found = {int(m.group(1)) for m in re.finditer(r"\b(202[0-6])\s*학년도", text)}
    found |= {int(m.group(1)) for m in re.finditer(r"\b(202[0-6])\b", text)}
    for m in re.finditer(r"(202[0-6])\s*(?:~|∼|-|–|—|부터)\s*(202[0-6])", text):
        start, end = int(m.group(1)), int(m.group(2))
        if start <= end:
            found.update(range(start, end + 1))
    return {y for y in found if y in YEARS}


def has_result_term(text: str) -> bool:
    compact = normalize_space(text)
    return any(term in compact for term in RESULT_TERMS)


def excluded_context(text: str) -> bool:
    compact = normalize_space(text)
    if not any(term in compact for term in EXCLUDE_TERMS):
        return False
    # General undergraduate result language can coexist with a navigation menu
    # containing excluded categories. Only reject short, focused blocks.
    return len(compact) < 500 or not any(x in compact for x in ("수시", "정시", "신입학", "학부"))


def is_attachment_url(url: str, label: str = "") -> bool:
    blob = (url + " " + label).lower()
    if re.search(r"\.(?:" + "|".join(ATTACHMENT_EXTS) + r")(?:$|[?&#])", blob):
        return True
    return any(token in blob for token in ("download", "filedown", "file_down", "attach", "atchfile", "bbsfile"))


def attachment_candidates(element, page_url: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    html = str(element)
    for anchor in element.find_all("a", href=True) if hasattr(element, "find_all") else []:
        href = anchor.get("href", "").strip()
        label = normalize_space(anchor.get_text(" ", strip=True))
        if href and not href.lower().startswith(("javascript:void", "#")):
            full = urljoin(page_url, href.replace("&amp;", "&"))
            if is_attachment_url(full, label):
                candidates.append((full, label))
        onclick = anchor.get("onclick", "")
        for raw in re.findall(r"['\"]([^'\"]+)['\"]", onclick):
            full = urljoin(page_url, raw.replace("&amp;", "&"))
            if is_attachment_url(full, label):
                candidates.append((full, label))
    for raw in re.findall(r"(?:https?://[^'\"\s<>]+|/[^'\"\s<>]+)", html):
        full = urljoin(page_url, raw.replace("&amp;", "&"))
        if is_attachment_url(full):
            candidates.append((full, ""))
    seen: set[str] = set()
    output: list[tuple[str, str]] = []
    for url, label in candidates:
        url = canonical_url(url)
        if url not in seen:
            seen.add(url)
            output.append((url, label))
    return output


def magic_extension(data: bytes, content_type: str, suggested: str) -> str:
    lower = suggested.lower()
    m = re.search(r"\.([a-z0-9]{2,5})(?:$|[?&#])", lower)
    if data.startswith(b"%PDF"):
        return ".pdf"
    if data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        if ".hwp" in lower or "hwp" in content_type.lower():
            return ".hwp"
        return ".xls"
    if data.startswith(b"PK"):
        for ext in (".hwpx", ".xlsx", ".pptx", ".docx", ".zip"):
            if ext in lower:
                return ext
        return ".zip"
    if m and m.group(1) in ATTACHMENT_EXTS:
        return "." + m.group(1)
    return ".bin"


def valid_download(data: bytes, content_type: str, suggested: str) -> bool:
    if len(data) < 128:
        return False
    head = data[:1000].lower()
    if b"<html" in head or b"<!doctype html" in head:
        return False
    ext = magic_extension(data, content_type, suggested)
    return ext != ".bin"


def save_document(data: bytes, ext: str, metadata: dict) -> dict:
    digest = sha256(data)
    target = CACHE / f"{digest}{ext}"
    if not target.exists():
        target.write_bytes(data)
    meta_path = CACHE / f"{digest}.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"sha256": digest, "cache_path": target.as_posix(), "extension": ext, "bytes": len(data)}


def save_html_snapshot(response: requests.Response, university: str, url: str, title: str) -> dict:
    data = response.content
    return save_document(data, ".html", {
        "university": university,
        "type": "official_html_snapshot",
        "source_url": url,
        "title": title,
        "content_type": response.headers.get("content-type", ""),
        "retrieved_at_epoch": int(time.time()),
    })


def fetch(url: str, referer: str | None = None) -> requests.Response | None:
    try:
        headers = {"Referer": referer} if referer else None
        response = SESSION.get(url, timeout=70, allow_redirects=True, headers=headers)
        if response.status_code != 200 or len(response.content) < 80:
            return None
        return response
    except requests.RequestException:
        return None


def decode_html(response: requests.Response) -> str:
    ctype = response.headers.get("content-type", "").lower()
    if "charset=" not in ctype:
        response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def pagination_variants(url: str) -> Iterable[str]:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    keys = ("page", "pageNo", "pageIndex", "nPage", "page_no", "p", "curPage")
    for key in keys:
        for value in range(2, 9):
            updated = dict(query)
            updated[key] = str(value)
            yield urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(updated), ""))


def likely_detail_link(anchor_text: str, href: str) -> bool:
    blob = normalize_space(anchor_text + " " + href)
    if any(term in blob for term in RESULT_TERMS):
        return True
    if extract_years(blob) and any(token in href.lower() for token in ("view", "detail", "select", "article", "board", "bbs", "result", "stat")):
        return True
    return False


def page_blocks(soup: BeautifulSoup):
    selectors = ("tr", "li", "article", ".board-list li", ".list li", ".bbs-list li", ".board_view", ".view", "section")
    yielded: set[int] = set()
    for selector in selectors:
        for node in soup.select(selector):
            ident = id(node)
            if ident in yielded:
                continue
            yielded.add(ident)
            text = normalize_space(node.get_text(" ", strip=True))
            if 8 <= len(text) <= 1600:
                yield node, text


def candidate_quality(page_url: str, attachment_count: int, text: str) -> int:
    if attachment_count:
        return 4
    path = page_url.lower()
    if any(token in path for token in ("view", "detail", "selectbbsntt", "article/")):
        return 3
    if len(extract_years(text)) == 1 and len(text) < 700:
        return 2
    return 1


def crawl_seed(seed: Seed, global_candidates: dict[tuple[str, int], dict], failures: list[dict]) -> None:
    queue: deque[tuple[str, int]] = deque((canonical_url(url), 0) for url in seed.urls)
    for url in seed.urls:
        for variant in pagination_variants(url):
            queue.append((canonical_url(variant), 1))
    visited: set[str] = set()
    pages = 0

    while queue and pages < seed.max_pages:
        url, depth = queue.popleft()
        if url in visited or not official_host(url, seed.domain_suffix):
            continue
        visited.add(url)
        response = fetch(url)
        if response is None:
            failures.append({"university": seed.university, "url": url, "reason": "fetch_failed"})
            continue
        ctype = response.headers.get("content-type", "").lower()
        if "html" not in ctype and not response.content.lstrip().startswith((b"<", b"\xef\xbb\xbf<")):
            continue
        pages += 1
        html_text = decode_html(response)
        soup = BeautifulSoup(html_text, "html.parser")
        title = normalize_space((soup.title.get_text(" ", strip=True) if soup.title else ""))
        page_snapshot: dict | None = None

        def ensure_snapshot() -> dict:
            nonlocal page_snapshot
            if page_snapshot is None:
                page_snapshot = save_html_snapshot(response, seed.university, url, title)
            return page_snapshot

        # Structured rows/cards are the primary evidence source.
        for node, text in page_blocks(soup):
            years = extract_years(text)
            if not years or not has_result_term(text) or excluded_context(text):
                continue
            attachment_docs: list[dict] = []
            attachment_urls: list[str] = []
            for file_url, label in attachment_candidates(node, url):
                if not official_host(file_url, seed.domain_suffix):
                    continue
                file_response = fetch(file_url, referer=url)
                if file_response is None:
                    continue
                data = file_response.content
                ctype_file = file_response.headers.get("content-type", "")
                if not valid_download(data, ctype_file, file_url + " " + label):
                    continue
                ext = magic_extension(data, ctype_file, file_url + " " + label)
                doc = save_document(data, ext, {
                    "university": seed.university,
                    "type": "official_attachment",
                    "source_page": url,
                    "direct_url": file_response.url,
                    "label": label,
                    "content_type": ctype_file,
                    "retrieved_at_epoch": int(time.time()),
                })
                attachment_docs.append(doc)
                attachment_urls.append(file_response.url)

            if not attachment_docs:
                attachment_docs = [ensure_snapshot()]

            quality = candidate_quality(url, len(attachment_urls), text)
            for year in years:
                key = (seed.university, year)
                if key in EXISTING_SLOTS:
                    continue
                candidate = {
                    "university": seed.university,
                    "year": year,
                    "quality": quality,
                    "source_type": "official_attachment" if attachment_urls else "official_webpage_snapshot",
                    "source_page_url": url,
                    "direct_file_urls": attachment_urls,
                    "evidence_text": text[:900],
                    "documents": attachment_docs,
                    "page_title": title,
                }
                old = global_candidates.get(key)
                if old is None or (candidate["quality"], len(candidate["direct_file_urls"])) > (old["quality"], len(old["direct_file_urls"])):
                    global_candidates[key] = candidate

            # Follow detail links found inside a relevant row/card.
            if depth < 3:
                for anchor in node.find_all("a", href=True):
                    href = anchor.get("href", "").strip()
                    if not href or href.lower().startswith(("javascript:void", "#")):
                        continue
                    full = canonical_url(urljoin(url, href.replace("&amp;", "&")))
                    if official_host(full, seed.domain_suffix) and likely_detail_link(anchor.get_text(" ", strip=True), href):
                        queue.append((full, depth + 1))

        # Some official pages display a compact year selector or a single
        # cumulative result page rather than row-based markup.
        body_text = normalize_space(soup.get_text(" ", strip=True))
        page_years = extract_years(body_text)
        if page_years and has_result_term(body_text) and not excluded_context(body_text):
            page_hint = normalize_space(title + " " + body_text[:1800])
            for year in page_years:
                key = (seed.university, year)
                if key in EXISTING_SLOTS or key in global_candidates:
                    continue
                global_candidates[key] = {
                    "university": seed.university,
                    "year": year,
                    "quality": 1,
                    "source_type": "official_webpage_snapshot",
                    "source_page_url": url,
                    "direct_file_urls": [],
                    "evidence_text": page_hint[:900],
                    "documents": [ensure_snapshot()],
                    "page_title": title,
                }

        # Follow relevant links from the full page.
        if depth < 2:
            for anchor in soup.find_all("a", href=True):
                href = anchor.get("href", "").strip()
                text = normalize_space(anchor.get_text(" ", strip=True))
                if not href or href.lower().startswith(("javascript:", "#", "mailto:")):
                    continue
                full = canonical_url(urljoin(url, href.replace("&amp;", "&")))
                if not official_host(full, seed.domain_suffix):
                    continue
                if likely_detail_link(text, href):
                    queue.append((full, depth + 1))


def main() -> int:
    failures: list[dict] = []
    candidates: dict[tuple[str, int], dict] = {}

    for index, seed in enumerate(SEEDS, start=1):
        crawl_seed(seed, candidates, failures)
        print(json.dumps({
            "seed": index,
            "university": seed.university,
            "candidate_slots": len(candidates),
        }, ensure_ascii=False), flush=True)
        # Continue beyond 200 to provide a quality buffer, but avoid excessive
        # crawling once enough independently sourced slots are available.
        if len(candidates) >= 235 and index >= 30:
            break

    ranked = sorted(
        candidates.values(),
        key=lambda x: (-x["quality"], x["university"], -x["year"], x["source_page_url"]),
    )
    selected = ranked[:200]

    if len(selected) < 200:
        summary = {
            "selected_slots": len(selected),
            "candidate_slots": len(candidates),
            "status": "failed_below_200",
            "failures": len(failures),
        }
        (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    # Copy each referenced original document once, keyed by SHA256.
    copied: dict[str, str] = {}
    for slot in selected:
        for doc in slot["documents"]:
            digest = doc["sha256"]
            if digest in copied:
                continue
            source = Path(doc["cache_path"])
            target = DOCS / f"{digest}{doc['extension']}"
            shutil.copy2(source, target)
            meta_source = CACHE / f"{digest}.json"
            if meta_source.exists():
                shutil.copy2(meta_source, DOCS / f"{digest}.json")
            copied[digest] = target.relative_to(FINAL).as_posix()

    rows: list[dict] = []
    for number, slot in enumerate(selected, start=1):
        doc_hashes = [doc["sha256"] for doc in slot["documents"]]
        doc_paths = [copied[h] for h in doc_hashes]
        pointer_dir = POINTERS / safe_name(slot["university"])
        pointer_dir.mkdir(parents=True, exist_ok=True)
        pointer = pointer_dir / f"{slot['year']}_입시결과.txt"
        pointer.write_text(
            "\n".join([
                f"관리번호: ADD-{number:03d}",
                f"대학: {slot['university']}",
                f"학년도: {slot['year']}",
                f"공식 출처 유형: {slot['source_type']}",
                f"공식 게시페이지: {slot['source_page_url']}",
                f"직접 파일 URL: {' | '.join(slot['direct_file_urls'])}",
                f"보존 문서: {' | '.join(doc_paths)}",
                f"SHA256: {' | '.join(doc_hashes)}",
                f"근거 문구: {slot['evidence_text']}",
            ]),
            encoding="utf-8",
        )
        rows.append({
            "management_id": f"ADD-{number:03d}",
            "university": slot["university"],
            "admission_year": slot["year"],
            "source_type": slot["source_type"],
            "quality_score": slot["quality"],
            "official_page_url": slot["source_page_url"],
            "direct_file_urls": " | ".join(slot["direct_file_urls"]),
            "document_sha256": " | ".join(doc_hashes),
            "document_paths": " | ".join(doc_paths),
            "pointer_path": pointer.relative_to(FINAL).as_posix(),
            "evidence_text": slot["evidence_text"],
        })

    with (FINAL / "slot_manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    source_rows: list[dict] = []
    for digest, rel_path in sorted(copied.items()):
        meta_path = DOCS / f"{digest}.json"
        metadata = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        source_rows.append({
            "sha256": digest,
            "document_path": rel_path,
            "bytes": (FINAL / rel_path).stat().st_size,
            "document_type": metadata.get("type", ""),
            "university": metadata.get("university", ""),
            "source_page": metadata.get("source_page", metadata.get("source_url", "")),
            "direct_url": metadata.get("direct_url", ""),
            "content_type": metadata.get("content_type", ""),
        })
    with (FINAL / "document_manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(source_rows[0]))
        writer.writeheader(); writer.writerows(source_rows)

    universities = sorted({row["university"] for row in rows})
    years_count = {str(y): sum(1 for row in rows if row["admission_year"] == y) for y in YEARS}
    source_count = {
        "official_attachment_slots": sum(1 for row in rows if row["source_type"] == "official_attachment"),
        "official_webpage_snapshot_slots": sum(1 for row in rows if row["source_type"] == "official_webpage_snapshot"),
    }
    summary = {
        "selected_unique_slots": len(rows),
        "slot_key": "university + admission_year",
        "existing_slots_excluded": len(EXISTING_SLOTS),
        "candidate_slots_found": len(candidates),
        "universities_covered": len(universities),
        "university_names": universities,
        "unique_original_documents": len(copied),
        "slots_by_year": years_count,
        **source_count,
        "failed_page_requests": len(failures),
        "status": "success_200_unique_slots",
    }
    (FINAL / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (FINAL / "failed_requests.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    (FINAL / "README.txt").write_text(
        "\n".join([
            "추가 공식 입시결과 200개 슬롯 수집본",
            "",
            "- 슬롯 정의: 대학명 + 입학 학년도(2020~2026)",
            "- 동일 대학·동일 학년도는 원본 파일이 여러 개여도 1개 슬롯으로 계산",
            "- 기존 2028 시행계획 및 기존 완료 대학·연도는 제외",
            "- 공식 첨부파일을 우선 저장",
            "- 첨부파일이 없는 공식 결과 페이지는 HTML 원본 보존본으로 저장",
            "- 동일 원본 문서는 SHA256 기준으로 한 번만 보존",
            "- slot_manifest.csv에서 200개 슬롯과 공식 출처를 확인 가능",
            "- documents 폴더에는 중복 제거된 원본/보존본이 저장됨",
        ]),
        encoding="utf-8",
    )

    # Remove temporary cache from final deliverable area.
    shutil.rmtree(CACHE, ignore_errors=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
