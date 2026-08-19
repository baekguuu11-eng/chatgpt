from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

OUT = Path("adiga500_output")
FINAL = OUT / "admissions_total_500"
DOCS = FINAL / "documents"
SLOTS = FINAL / "slots"
for p in (DOCS, SLOTS):
    p.mkdir(parents=True, exist_ok=True)

UNIVERSITY_DATA_URL = (
    "https://raw.githubusercontent.com/thehouserehab/reperformance-homepage/"
    "dd3eb31464458f5482e93f8b7178b4e70c7e7b54/"
    "app/pe-exam/adigaRegularAdmissionData.ts"
)
SELECTION_PAGE_URL = "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do"
SELECTION_AJAX_URL = "https://www.adiga.kr/uct/acd/ade/criteriaAndResultItemNewAjax.do"

# canonical|expected area|aliases separated by comma
TARGET_DATA = r"""
서울대학교|서울|서울대학교
연세대학교|서울|연세대학교
고려대학교|서울|고려대학교
서강대학교|서울|서강대학교
성균관대학교|서울|성균관대학교
한양대학교 서울캠퍼스|서울|한양대학교
중앙대학교|서울|중앙대학교
경희대학교|서울|경희대학교
한국외국어대학교|서울|한국외국어대학교
서울시립대학교|서울|서울시립대학교
건국대학교 서울캠퍼스|서울|건국대학교
동국대학교 서울캠퍼스|서울|동국대학교
홍익대학교 서울캠퍼스|서울|홍익대학교
국민대학교|서울|국민대학교
숭실대학교|서울|숭실대학교
세종대학교|서울|세종대학교
광운대학교|서울|광운대학교
명지대학교 서울캠퍼스|서울|명지대학교
상명대학교 서울캠퍼스|서울|상명대학교
한성대학교|서울|한성대학교
서경대학교|서울|서경대학교
삼육대학교|서울|삼육대학교
성공회대학교|서울|성공회대학교
서울과학기술대학교|서울|서울과학기술대학교
한양대학교 ERICA캠퍼스|경기|한양대학교(ERICA),한양대학교
아주대학교|경기|아주대학교
가천대학교|경기|가천대학교
단국대학교 죽전캠퍼스|경기|단국대학교
한국항공대학교|경기|한국항공대학교
한국공학대학교|경기|한국공학대학교,한국산업기술대학교
경기대학교|경기|경기대학교
가톨릭대학교|경기|가톨릭대학교
한경국립대학교|경기|한경국립대학교,한경대학교
수원대학교|경기|수원대학교
강남대학교|경기|강남대학교
한신대학교|경기|한신대학교
대진대학교|경기|대진대학교
용인대학교|경기|용인대학교
을지대학교|경기|을지대학교
신한대학교|경기|신한대학교
안양대학교|경기|안양대학교
성결대학교|경기|성결대학교
한세대학교|경기|한세대학교
협성대학교|경기|협성대학교
평택대학교|경기|평택대학교
차의과학대학교|경기|차의과학대학교
중부대학교 고양캠퍼스|경기|중부대학교
경동대학교 메트로폴캠퍼스|경기|경동대학교
동양대학교 동두천캠퍼스|경기|동양대학교
화성의과학대학교|경기|화성의과학대학교,신경대학교
인하대학교|인천|인하대학교
인천대학교|인천|인천대학교
청운대학교 인천캠퍼스|인천|청운대학교
강원대학교|강원|강원대학교
경북대학교|대구|경북대학교
경상국립대학교|경남|경상국립대학교,경상대학교
부산대학교|부산|부산대학교
전남대학교|광주|전남대학교
전북대학교|전북|전북대학교
제주대학교|제주|제주대학교
충남대학교|대전|충남대학교
충북대학교|충북|충북대학교
국립공주대학교|충남|공주대학교,국립공주대학교
국립한국교통대학교|충북|한국교통대학교,국립한국교통대학교
국립한밭대학교|대전|한밭대학교,국립한밭대학교
국립부경대학교|부산|부경대학교,국립부경대학교
국립창원대학교|경남|창원대학교,국립창원대학교
국립금오공과대학교|경북|금오공과대학교,국립금오공과대학교
국립경국대학교|경북|국립경국대학교,안동대학교,국립안동대학교
국립한국해양대학교|부산|한국해양대학교,국립한국해양대학교
국립군산대학교|전북|군산대학교,국립군산대학교
국립목포대학교|전남|목포대학교,국립목포대학교
국립순천대학교|전남|순천대학교,국립순천대학교
국립목포해양대학교|전남|목포해양대학교,국립목포해양대학교
한국기술교육대학교|충남|한국기술교육대학교
KAIST|대전|한국과학기술원,KAIST
GIST|광주|광주과학기술원,GIST
DGIST|대구|대구경북과학기술원,DGIST
UNIST|울산|울산과학기술원,UNIST
한국에너지공과대학교|전남|한국에너지공과대학교
POSTECH|경북|포항공과대학교,POSTECH
고려대학교 세종캠퍼스|세종|고려대학교(세종),고려대학교
연세대학교 미래캠퍼스|강원|연세대학교(미래),연세대학교
건국대학교 글로컬캠퍼스|충북|건국대학교(글로컬),건국대학교
홍익대학교 세종캠퍼스|세종|홍익대학교
단국대학교 천안캠퍼스|충남|단국대학교
동국대학교 WISE캠퍼스|경북|동국대학교(WISE),동국대학교
순천향대학교|충남|순천향대학교
한림대학교|강원|한림대학교
한동대학교|경북|한동대학교
울산대학교|울산|울산대학교
영남대학교|경북|영남대학교
계명대학교|대구|계명대학교
동아대학교|부산|동아대학교
조선대학교|광주|조선대학교
원광대학교|전북|원광대학교
호서대학교|충남|호서대학교
선문대학교|충남|선문대학교
"""

TARGETS = []
for line in TARGET_DATA.strip().splitlines():
    canonical, area, aliases = line.split("|", 2)
    TARGETS.append({
        "canonical": canonical,
        "area": area,
        "aliases": [x.strip() for x in aliases.split(",") if x.strip()],
    })

_tls = threading.local()


def client() -> requests.Session:
    if not hasattr(_tls, "session"):
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36 AdmissionsArchive/3.0",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
        })
        _tls.session = s
    return _tls.session


def normalize(value: str) -> str:
    value = re.sub(r"\([^)]*\)", "", value or "")
    value = re.sub(r"(?:국립|대학교|캠퍼스|본교|분교|제\d캠퍼스)", "", value)
    return re.sub(r"[\s·ㆍ_\-/]", "", value).lower()


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_document(data: bytes, suffix: str, metadata: dict) -> tuple[str, str]:
    digest = sha256(data)
    target = DOCS / f"{digest}{suffix}"
    if not target.exists():
        target.write_bytes(data)
        (DOCS / f"{digest}.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return digest, target.relative_to(FINAL).as_posix()


def load_universities() -> list[dict]:
    r = requests.get(UNIVERSITY_DATA_URL, timeout=90, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    source = r.text
    start = source.index("{")
    end = source.lastIndex if False else source.rfind(" as const")
    payload = json.loads(source[start:end])
    return [u for u in payload["universities"] if u.get("schoolType") == "4년제"]


def alias_score(target: dict, university: dict) -> int:
    uname = university.get("name", "")
    unorm = normalize(uname)
    score = 0
    for alias in target["aliases"]:
        anorm = normalize(alias)
        if unorm == anorm:
            score = max(score, 100)
        elif anorm and (anorm in unorm or unorm in anorm):
            score = max(score, 75)
    if university.get("area") == target["area"]:
        score += 20
    canonical = target["canonical"]
    campus = university.get("campus", "")
    if "ERICA" in canonical and ("ERICA" in uname.upper() or target["area"] == university.get("area")):
        score += 25
    if "글로컬" in canonical and "글로컬" in uname:
        score += 30
    if "미래" in canonical and "미래" in uname:
        score += 30
    if "WISE" in canonical and "WISE" in uname.upper():
        score += 30
    if "세종캠퍼스" in canonical and target["area"] == university.get("area"):
        score += 20
    if "천안캠퍼스" in canonical and target["area"] == university.get("area"):
        score += 20
    if "서울캠퍼스" in canonical and university.get("area") == "서울":
        score += 15
    if "죽전캠퍼스" in canonical and university.get("area") == "경기":
        score += 15
    if "고양캠퍼스" in canonical and university.get("area") == "경기":
        score += 15
    if "인천캠퍼스" in canonical and university.get("area") == "인천":
        score += 15
    if campus == "본교":
        score += 2
    return score


def map_target_codes(universities: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    mapping: dict[str, list[dict]] = {}
    audit: list[dict] = []
    for target in TARGETS:
        ranked = sorted(
            ((alias_score(target, u), u) for u in universities),
            key=lambda x: x[0],
            reverse=True,
        )
        accepted = [u for score, u in ranked if score >= 90]
        if not accepted and ranked and ranked[0][0] >= 75:
            accepted = [ranked[0][1]]
        # Keep all codes tied to the same target name/area. Integrated universities
        # can publish results separately by campus; the slot aggregates them.
        if accepted:
            best_score = alias_score(target, accepted[0])
            accepted = [u for u in accepted if alias_score(target, u) >= best_score - 10]
        mapping[target["canonical"]] = accepted
        audit.append({
            "canonical": target["canonical"],
            "expected_area": target["area"],
            "matches": [
                {"code": u.get("code"), "name": u.get("name"), "area": u.get("area"), "campus": u.get("campus"), "score": alias_score(target, u)}
                for u in accepted
            ],
            "top_candidates": [
                {"code": u.get("code"), "name": u.get("name"), "area": u.get("area"), "campus": u.get("campus"), "score": score}
                for score, u in ranked[:3]
            ],
        })
    return mapping, audit


def result_response_valid(text: str) -> tuple[bool, int, str]:
    if not text or len(text) < 300:
        return False, 0, ""
    soup = BeautifulSoup(text, "html.parser")
    plain = clean_text(soup.get_text(" ", strip=True))
    result_blocks = len(soup.select(".tbAdmRes")) + text.count('class="tbAdmRes"')
    tables = soup.find_all("table")
    row_count = sum(len(table.find_all("tr")) for table in tables)
    has_metrics = any(x in plain for x in ("경쟁률", "70%", "50%", "충원", "최종등록", "환산점수", "백분위"))
    has_result_heading = any(x in plain for x in ("전형 결과", "전형결과", "입시 결과", "입시결과"))
    valid = (result_blocks > 0 or row_count >= 3) and has_metrics and has_result_heading
    return valid, row_count, plain[:1200]


def fetch_one_response(unv: dict, result_year: int, search_year: int, up_code: str) -> dict | None:
    unv_code = str(unv["code"])
    page_params = urlencode({"menuId": "PCUVTINF2000", "searchSyr": str(search_year), "unvCd": unv_code})
    page_url = f"{SELECTION_PAGE_URL}?{page_params}"
    s = client()
    try:
        page = s.get(page_url, timeout=35)
        if page.status_code != 200:
            return None
        form = {
            "searchSyr": str(search_year),
            "unvCd": unv_code,
            "tsrdCmphSlcnArtclUpCd": up_code,
            "compUnvCd": "",
        }
        r = s.post(
            SELECTION_AJAX_URL,
            data=form,
            timeout=40,
            headers={"Referer": page_url, "X-Requested-With": "XMLHttpRequest"},
        )
        if r.status_code != 200:
            return None
        valid, rows, snippet = result_response_valid(r.text)
        if not valid:
            return None
        digest, rel_path = save_document(r.content, ".html", {
            "type": "official_adiga_university_result_html",
            "source": "대입정보포털 어디가 평가기준·입시결과",
            "university_code": unv_code,
            "university_name": unv.get("name"),
            "area": unv.get("area"),
            "campus": unv.get("campus"),
            "result_year": result_year,
            "search_school_year": search_year,
            "selection_up_code": up_code,
            "selection_page_url": page_url,
            "ajax_url": SELECTION_AJAX_URL,
            "rows_detected": rows,
            "sha256": sha256(r.content),
        })
        return {
            "university_code": unv_code,
            "university_name": unv.get("name"),
            "area": unv.get("area"),
            "campus": unv.get("campus"),
            "result_year": result_year,
            "search_school_year": search_year,
            "selection_up_code": up_code,
            "selection_page_url": page_url,
            "ajax_url": SELECTION_AJAX_URL,
            "row_count": rows,
            "snippet": snippet,
            "sha256": digest,
            "document_path": rel_path,
        }
    except requests.RequestException:
        return None


def collect_result_slot(canonical: str, codes: list[dict], result_year: int) -> dict | None:
    documents: dict[str, dict] = {}
    # ADIGA's current page uses school year N while exposing result year N-1.
    # The same-year request is retained as a historical fallback.
    for search_year in (result_year + 1, result_year):
        for unv in codes:
            for up_code in ("30", "40", "20", "10"):
                item = fetch_one_response(unv, result_year, search_year, up_code)
                if item:
                    documents[item["sha256"]] = item
        if documents:
            break
    if not documents:
        return None
    docs = list(documents.values())
    return {
        "university": canonical,
        "year": result_year,
        "slot_type": "입시결과",
        "source_type": "대입정보포털 어디가 대학별 공식 제출결과",
        "source_url": docs[0]["selection_page_url"],
        "documents": docs,
        "document_hashes": [d["sha256"] for d in docs],
        "document_paths": [d["document_path"] for d in docs],
    }


def normalize_plan_name(value: str) -> str:
    value = re.sub(r"\[[^]]*\]", "", value)
    value = value.replace("_2028_시행계획(1차수)", "")
    value = Path(value).stem
    return normalize(value)


def add_2028_slots(slots: dict[tuple[str, int], dict]) -> None:
    source_root = Path("output/official_documents")
    if not source_root.exists():
        return
    files = [p for p in source_root.rglob("*") if p.is_file()]
    for target in TARGETS:
        best: Path | None = None
        best_score = -1
        for p in files:
            filename = p.name
            pnorm = normalize_plan_name(filename)
            score = 0
            for alias in target["aliases"]:
                anorm = normalize(alias)
                if pnorm == anorm:
                    score = max(score, 100)
                elif anorm and (anorm in pnorm or pnorm in anorm):
                    score = max(score, 75)
            if f"[{target['area']}]" in filename:
                score += 20
            if "ERICA" in target["canonical"] and "ERICA" in filename.upper():
                score += 30
            if "글로컬" in target["canonical"] and "글로컬" in filename:
                score += 30
            if "미래" in target["canonical"] and "미래" in filename:
                score += 30
            if "WISE" in target["canonical"] and "WISE" in filename.upper():
                score += 30
            if score > best_score:
                best_score, best = score, p
        if best is None or best_score < 90:
            continue
        data = best.read_bytes()
        digest, rel_path = save_document(data, best.suffix.lower(), {
            "type": "official_adiga_2028_plan",
            "source": "대입정보포털 어디가 공식 2028 시행계획 묶음",
            "university": target["canonical"],
            "original_name": best.name,
            "sha256": sha256(data),
        })
        slots[(target["canonical"], 2028)] = {
            "university": target["canonical"],
            "year": 2028,
            "slot_type": "시행계획",
            "source_type": "대입정보포털 어디가 공식 시행계획 원본",
            "source_url": "https://www.adiga.kr/uct/ces/archiveView.do?menuId=PCUCTCES1000",
            "documents": [{"sha256": digest, "document_path": rel_path, "original_name": best.name}],
            "document_hashes": [digest],
            "document_paths": [rel_path],
        }


def main() -> int:
    universities = load_universities()
    code_mapping, mapping_audit = map_target_codes(universities)
    (FINAL / "university_code_mapping.json").write_text(
        json.dumps(mapping_audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    slots: dict[tuple[str, int], dict] = {}
    add_2028_slots(slots)
    initial_2028 = len(slots)

    tasks = []
    with ThreadPoolExecutor(max_workers=24) as executor:
        for target in TARGETS:
            canonical = target["canonical"]
            codes = code_mapping.get(canonical, [])
            if not codes:
                continue
            for year in range(2020, 2027):
                tasks.append(executor.submit(collect_result_slot, canonical, codes, year))
        completed = 0
        for future in as_completed(tasks):
            completed += 1
            try:
                slot = future.result()
            except Exception:
                slot = None
            if slot:
                slots[(slot["university"], slot["year"])] = slot
            if completed % 50 == 0:
                print(json.dumps({
                    "processed_result_tasks": completed,
                    "total_result_tasks": len(tasks),
                    "slots_collected": len(slots),
                }, ensure_ascii=False), flush=True)

    ranked = sorted(
        slots.values(),
        key=lambda s: (0 if s["year"] == 2028 else 1, s["university"], -s["year"]),
    )
    selected = ranked[:500]

    rows: list[dict] = []
    for index, slot in enumerate(selected, start=1):
        pointer_dir = SLOTS / re.sub(r"[<>:\"/\\|?*]+", "_", slot["university"])
        pointer_dir.mkdir(parents=True, exist_ok=True)
        pointer = pointer_dir / f"{slot['year']}_{slot['slot_type']}.txt"
        pointer.write_text("\n".join([
            f"관리번호: SLOT-{index:03d}",
            f"대학: {slot['university']}",
            f"학년도: {slot['year']}",
            f"자료유형: {slot['slot_type']}",
            f"출처유형: {slot['source_type']}",
            f"공식URL: {slot['source_url']}",
            f"보존문서: {' | '.join(slot['document_paths'])}",
            f"SHA256: {' | '.join(slot['document_hashes'])}",
        ]), encoding="utf-8")
        rows.append({
            "management_id": f"SLOT-{index:03d}",
            "university": slot["university"],
            "admission_year": slot["year"],
            "slot_type": slot["slot_type"],
            "source_type": slot["source_type"],
            "official_url": slot["source_url"],
            "document_paths": " | ".join(slot["document_paths"]),
            "sha256": " | ".join(slot["document_hashes"]),
            "pointer_path": pointer.relative_to(FINAL).as_posix(),
        })

    manifest_fields = [
        "management_id", "university", "admission_year", "slot_type",
        "source_type", "official_url", "document_paths", "sha256", "pointer_path",
    ]
    with (FINAL / "slot_manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=manifest_fields)
        writer.writeheader()
        writer.writerows(rows)

    unique_keys = {(row["university"], int(row["admission_year"])) for row in rows}
    summary = {
        "target_total_slots": 784,
        "requested_completed_slots": 500,
        "selected_slots": len(rows),
        "unique_slot_keys": len(unique_keys),
        "all_slots_found_before_selection": len(slots),
        "official_2028_plan_slots": initial_2028,
        "adiga_university_result_slots_found": sum(1 for s in slots.values() if s["slot_type"] == "입시결과"),
        "universities_with_codes": sum(1 for value in code_mapping.values() if value),
        "universities_without_codes": [key for key, value in code_mapping.items() if not value],
        "unique_documents_in_selected": len({h for s in selected for h in s["document_hashes"]}),
        "status": "success" if len(rows) == 500 and len(unique_keys) == 500 else "failed_below_500",
    }
    (FINAL / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (FINAL / "README.txt").write_text("\n".join([
        "98개 대학·캠퍼스 입시자료 500슬롯 수집본",
        "",
        "- 슬롯 단위: 대학명 + 입학 학년도",
        "- 2020~2026 입시결과: 대입정보포털 어디가 대학별 평가기준·입시결과 공개 응답 원본 HTML",
        "- 2028 시행계획: 대입정보포털 어디가 공식 일괄 배포 원본",
        "- 동일 대학·동일 학년도는 여러 수시·정시 문서가 있어도 1슬롯으로 계산",
        "- HTML 원본은 어디가가 대학별 제출 결과표를 반환한 공개 응답이며 단순 검색결과가 아님",
        "- 파일마다 SHA256과 공식 URL을 기록",
        "- slot_manifest.csv의 고유 대학×학년도 키가 정확히 500개일 때만 성공",
    ]), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0 if summary["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
