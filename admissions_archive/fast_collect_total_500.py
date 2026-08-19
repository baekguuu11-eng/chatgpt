from __future__ import annotations

import csv, hashlib, json, re, shutil, threading, time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT=Path('total500_output'); FINAL=ROOT/'total_500_slots'; DOCS=FINAL/'documents'; SLOTS=FINAL/'slots'
for p in (DOCS,SLOTS): p.mkdir(parents=True,exist_ok=True)
YEARS=range(2020,2027)
RESULT_TERMS=('입시결과','입시 결과','전형결과','전형 결과','입학전형 결과','입학전형결과','전형통계','입시통계','합격자 성적','등록자 성적','최종등록자')
EXCLUDE=('편입','재외국민','외국인','대학원')
FILE_EXTS=('pdf','hwp','hwpx','xls','xlsx','csv','zip','ppt','pptx','doc','docx')

# canonical|official domain suffix|search label|2028 archive base name|2028 region
DATA='''
서울대학교|snu.ac.kr|서울대학교|서울대학교|서울
연세대학교|yonsei.ac.kr|연세대학교 서울|연세대학교|서울
고려대학교|korea.ac.kr|고려대학교 서울|고려대학교|서울
서강대학교|sogang.ac.kr|서강대학교|서강대학교|서울
성균관대학교|skku.edu|성균관대학교|성균관대학교|서울
한양대학교 서울캠퍼스|hanyang.ac.kr|한양대학교 서울캠퍼스|한양대학교|서울
중앙대학교|cau.ac.kr|중앙대학교|중앙대학교|서울
경희대학교|khu.ac.kr|경희대학교|경희대학교|서울
한국외국어대학교|hufs.ac.kr|한국외국어대학교|한국외국어대학교|서울
서울시립대학교|uos.ac.kr|서울시립대학교|서울시립대학교|서울
건국대학교 서울캠퍼스|konkuk.ac.kr|건국대학교 서울캠퍼스|건국대학교|서울
동국대학교 서울캠퍼스|dongguk.edu|동국대학교 서울캠퍼스|동국대학교|서울
홍익대학교 서울캠퍼스|hongik.ac.kr|홍익대학교 서울캠퍼스|홍익대학교|서울
국민대학교|kookmin.ac.kr|국민대학교|국민대학교|서울
숭실대학교|ssu.ac.kr|숭실대학교|숭실대학교|서울
세종대학교|sejong.ac.kr|세종대학교|세종대학교|서울
광운대학교|kw.ac.kr|광운대학교|광운대학교|서울
명지대학교 서울캠퍼스|mju.ac.kr|명지대학교 서울캠퍼스|명지대학교|서울
상명대학교 서울캠퍼스|smu.ac.kr|상명대학교 서울캠퍼스|상명대학교|서울
한성대학교|hansung.ac.kr|한성대학교|한성대학교|서울
서경대학교|sku.ac.kr|서경대학교|서경대학교|서울
삼육대학교|syu.ac.kr|삼육대학교|삼육대학교|서울
성공회대학교|skhu.ac.kr|성공회대학교|성공회대학교|서울
서울과학기술대학교|seoultech.ac.kr|서울과학기술대학교|서울과학기술대학교|서울
한양대학교 ERICA캠퍼스|hanyang.ac.kr|한양대학교 ERICA|한양대학교(ERICA)|경기
아주대학교|ajou.ac.kr|아주대학교|아주대학교|경기
가천대학교|gachon.ac.kr|가천대학교|가천대학교|경기
단국대학교 죽전캠퍼스|dankook.ac.kr|단국대학교 죽전|단국대학교|경기
한국항공대학교|kau.ac.kr|한국항공대학교|한국항공대학교|경기
한국공학대학교|tukorea.ac.kr|한국공학대학교|한국공학대학교|경기
경기대학교|kyonggi.ac.kr|경기대학교|경기대학교|경기
가톨릭대학교|catholic.ac.kr|가톨릭대학교|가톨릭대학교|경기
한경국립대학교|hknu.ac.kr|한경국립대학교|한경국립대학교|경기
수원대학교|suwon.ac.kr|수원대학교|수원대학교|경기
강남대학교|kangnam.ac.kr|강남대학교|강남대학교|경기
한신대학교|hs.ac.kr|한신대학교|한신대학교|경기
대진대학교|daejin.ac.kr|대진대학교|대진대학교|경기
용인대학교|yongin.ac.kr|용인대학교|용인대학교|경기
을지대학교|eulji.ac.kr|을지대학교|을지대학교|경기
신한대학교|shinhan.ac.kr|신한대학교|신한대학교|경기
안양대학교|anyang.ac.kr|안양대학교|안양대학교|경기
성결대학교|sungkyul.ac.kr|성결대학교|성결대학교|경기
한세대학교|hansei.ac.kr|한세대학교|한세대학교|경기
협성대학교|uh.ac.kr|협성대학교|협성대학교|경기
평택대학교|pt.ac.kr|평택대학교|평택대학교|경기
차의과학대학교|cha.ac.kr|차의과학대학교|차의과학대학교|경기
중부대학교 고양캠퍼스|joongbu.ac.kr|중부대학교 고양캠퍼스||
경동대학교 메트로폴캠퍼스|kduniv.ac.kr|경동대학교 메트로폴캠퍼스||
동양대학교 동두천캠퍼스|dyu.ac.kr|동양대학교 동두천캠퍼스||
화성의과학대학교|hsmu.ac.kr|화성의과학대학교|화성의과학대학교|경기
인하대학교|inha.ac.kr|인하대학교|인하대학교|인천
인천대학교|inu.ac.kr|인천대학교|인천대학교|인천
청운대학교 인천캠퍼스|chungwoon.ac.kr|청운대학교 인천캠퍼스||
강원대학교|kangwon.ac.kr|강원대학교|강원대학교|강원
경북대학교|knu.ac.kr|경북대학교|경북대학교|대구
경상국립대학교|gnu.ac.kr|경상국립대학교|경상국립대학교|경남
부산대학교|pusan.ac.kr|부산대학교|부산대학교|부산
전남대학교|jnu.ac.kr|전남대학교|전남대학교|광주
전북대학교|jbnu.ac.kr|전북대학교|전북대학교|전북
제주대학교|jejunu.ac.kr|제주대학교|제주대학교|제주
충남대학교|cnu.ac.kr|충남대학교|충남대학교|대전
충북대학교|cbnu.ac.kr|충북대학교|충북대학교|충북
국립공주대학교|kongju.ac.kr|국립공주대학교|국립공주대학교|충남
국립한국교통대학교|ut.ac.kr|국립한국교통대학교|국립한국교통대학교|충북
국립한밭대학교|hanbat.ac.kr|국립한밭대학교|국립한밭대학교|대전
국립부경대학교|pknu.ac.kr|국립부경대학교|국립부경대학교|부산
국립창원대학교|changwon.ac.kr|국립창원대학교|국립창원대학교|경남
국립금오공과대학교|kumoh.ac.kr|국립금오공과대학교|국립금오공과대학교|경북
국립경국대학교|gknu.ac.kr|국립경국대학교|국립경국대학교|경북
국립한국해양대학교|kmou.ac.kr|국립한국해양대학교|국립한국해양대학교|부산
국립군산대학교|kunsan.ac.kr|국립군산대학교|국립군산대학교|전북
국립목포대학교|mokpo.ac.kr|국립목포대학교|국립목포대학교|전남
국립순천대학교|scnu.ac.kr|국립순천대학교|국립순천대학교|전남
국립목포해양대학교|mmu.ac.kr|국립목포해양대학교|국립목포해양대학교|전남
한국기술교육대학교|koreatech.ac.kr|한국기술교육대학교|한국기술교육대학교|충남
KAIST|kaist.ac.kr|KAIST 한국과학기술원||
GIST|gist.ac.kr|GIST 광주과학기술원||
DGIST|dgist.ac.kr|DGIST 대구경북과학기술원||
UNIST|unist.ac.kr|UNIST 울산과학기술원||
한국에너지공과대학교|kentech.ac.kr|한국에너지공과대학교||
POSTECH|postech.ac.kr|POSTECH 포항공과대학교|포항공과대학교|경북
고려대학교 세종캠퍼스|korea.ac.kr|고려대학교 세종캠퍼스|고려대학교(세종)|세종
연세대학교 미래캠퍼스|yonsei.ac.kr|연세대학교 미래캠퍼스|연세대학교(미래)|강원
건국대학교 글로컬캠퍼스|kku.ac.kr|건국대학교 글로컬캠퍼스|건국대학교(글로컬)|충북
홍익대학교 세종캠퍼스|hongik.ac.kr|홍익대학교 세종캠퍼스|홍익대학교|세종
단국대학교 천안캠퍼스|dankook.ac.kr|단국대학교 천안캠퍼스|단국대학교|충남
동국대학교 WISE캠퍼스|dongguk.ac.kr|동국대학교 WISE캠퍼스|동국대학교(WISE)|경북
순천향대학교|sch.ac.kr|순천향대학교|순천향대학교|충남
한림대학교|hallym.ac.kr|한림대학교|한림대학교|강원
한동대학교|handong.edu|한동대학교|한동대학교|경북
울산대학교|ulsan.ac.kr|울산대학교|울산대학교|울산
영남대학교|yu.ac.kr|영남대학교|영남대학교|경북
계명대학교|kmu.ac.kr|계명대학교|계명대학교|대구
동아대학교|donga.ac.kr|동아대학교|동아대학교|부산
조선대학교|chosun.ac.kr|조선대학교|조선대학교|광주
원광대학교|wku.ac.kr|원광대학교|원광대학교|전북
호서대학교|hoseo.edu|호서대학교|호서대학교|충남
선문대학교|sunmoon.ac.kr|선문대학교|선문대학교|충남
'''
TARGETS=[]
for line in DATA.strip().splitlines():
    c,d,q,p,r=(line.split('|')+['',''])[:5]; TARGETS.append({'canonical':c,'domain':d,'query':q,'plan':p,'region':r})

_tls=threading.local()
def session():
    if not hasattr(_tls,'s'):
        s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36','Accept-Language':'ko-KR,ko;q=0.9,en;q=0.6'}); _tls.s=s
    return _tls.s

def official(url,domain):
    h=(urlparse(url).hostname or '').lower(); d=domain.lower(); return h==d or h.endswith('.'+d)
def norm(s): return re.sub(r'\s+',' ',s or '').strip()
def years(text): return {int(x) for x in re.findall(r'\b(202[0-6])\s*학년도',text)}
def result_text(text): return any(t in text for t in RESULT_TERMS) and not (len(text)<450 and any(x in text for x in EXCLUDE))
def sha(data): return hashlib.sha256(data).hexdigest()
def safe(s): return re.sub(r'[<>:"/\\|?*]+','_',norm(s))[:160] or 'unnamed'
def bing(query):
    u='https://www.bing.com/search?q='+quote_plus(query)+'&format=rss'
    try:
        r=session().get(u,timeout=18); r.raise_for_status(); root=ET.fromstring(r.content)
        out=[]
        for item in root.findall('.//item'):
            link=item.findtext('link') or ''; title=item.findtext('title') or ''; desc=item.findtext('description') or ''
            out.append((link,norm(title+' '+desc)))
        return out
    except Exception: return []
def get(url,referer=''):
    try:
        r=session().get(url,timeout=22,allow_redirects=True,headers={'Referer':referer} if referer else None)
        if r.status_code==200 and len(r.content)>100:return r
    except Exception: pass
    return None
def ext_magic(data,ctype,hint):
    low=(ctype+' '+hint).lower()
    if data.startswith(b'%PDF'):return '.pdf'
    if data.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):return '.hwp' if 'hwp' in low else '.xls'
    if data.startswith(b'PK'):
        for e in ('.hwpx','.xlsx','.pptx','.docx','.zip'):
            if e in low:return e
        return '.zip'
    m=re.search(r'\.('+'|'.join(FILE_EXTS)+r')(?:$|[?&#])',low); return '.'+m.group(1) if m else ''
def save_doc(data,ext,meta):
    h=sha(data); p=DOCS/(h+ext)
    if not p.exists(): p.write_bytes(data); (DOCS/(h+'.json')).write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    return h,p.relative_to(FINAL).as_posix()
def attachment_urls(soup,base):
    out=[]
    for a in soup.find_all('a'):
        label=norm(a.get_text(' ',strip=True)); blobs=[a.get('href') or '']+re.findall(r"['\"]([^'\"]+)['\"]",a.get('onclick') or '')
        for raw in blobs:
            if not raw or raw.startswith(('#','javascript:void')):continue
            u=urljoin(base,raw.replace('&amp;','&')); low=(u+' '+label).lower()
            if re.search(r'\.('+'|'.join(FILE_EXTS)+r')(?:$|[?&#])',low) or any(x in low for x in ('download','filedown','file_down','attach','atchfile','bbsfile')): out.append((u,label))
    seen=set(); return [(u,l) for u,l in out if not (u in seen or seen.add(u))]
def detail_links(soup,base,year):
    out=[]
    for a in soup.find_all('a',href=True):
        text=norm(a.get_text(' ',strip=True)); href=a['href']; blob=text+' '+href
        if str(year) in blob and result_text(blob):
            u=urljoin(base,href); out.append(u)
    seen=set(); return [u for u in out if not (u in seen or seen.add(u))][:6]
def process_url(url,target,year,depth=0):
    if not official(url,target['domain']): return None
    r=get(url); 
    if not r:return None
    ctype=r.headers.get('content-type',''); e=ext_magic(r.content,ctype,r.url)
    if e and b'<html' not in r.content[:500].lower():
        h,p=save_doc(r.content,e,{'type':'official_attachment','university':target['canonical'],'year':year,'url':r.url,'content_type':ctype}); return {'source_type':'원본파일','url':r.url,'hash':h,'path':p}
    try:
        r.encoding=r.apparent_encoding or r.encoding; soup=BeautifulSoup(r.text,'html.parser')
    except Exception:return None
    title=norm(soup.title.get_text(' ',strip=True) if soup.title else '')
    body=norm(soup.get_text(' ',strip=True))
    # Download official attachments from an exact result detail page.
    if year in years(title+' '+body[:4000]) and result_text(title+' '+body[:4000]):
        for fu,label in attachment_urls(soup,r.url)[:12]:
            if not official(fu,target['domain']):continue
            fr=get(fu,r.url)
            if not fr:continue
            fe=ext_magic(fr.content,fr.headers.get('content-type',''),fu+' '+label)
            if fe and b'<html' not in fr.content[:500].lower():
                h,p=save_doc(fr.content,fe,{'type':'official_attachment','university':target['canonical'],'year':year,'source_page':r.url,'url':fr.url,'label':label}); return {'source_type':'원본파일','url':r.url,'direct_url':fr.url,'hash':h,'path':p}
        likely_detail=any(x in r.url.lower() for x in ('view','detail','board_seq','bbs_seq','idx=','article','selectbbsntt','ntt')) or (str(year) in title and result_text(title))
        if likely_detail and len(body)>150:
            h,p=save_doc(r.content,'.html',{'type':'official_webpage_snapshot','university':target['canonical'],'year':year,'url':r.url,'title':title}); return {'source_type':'공식웹페이지보존본','url':r.url,'hash':h,'path':p}
    if depth==0:
        for du in detail_links(soup,r.url,year):
            z=process_url(du,target,year,1)
            if z:return z
    return None
def collect_slot(target,year):
    queries=[f'site:{target["domain"]} "{year}학년도" "입시결과" "{target["query"]}"',f'site:{target["domain"]} "{year}학년도" ("전형결과" OR "입학전형 결과" OR "전형통계")']
    candidates=[]
    for q in queries:
        for u,text in bing(q):
            if official(u,target['domain']) and str(year) in text and result_text(text): candidates.append(u)
        if candidates:break
    seen=set()
    for u in candidates[:6]:
        if u in seen:continue
        seen.add(u); z=process_url(u,target,year)
        if z:return target['canonical'],year,z
    return None

def add_plan_slots(slots):
    base=Path('output/official_documents')
    if not base.exists():return
    files=[p for p in base.rglob('*') if p.is_file()]
    for t in TARGETS:
        if not t['plan']:continue
        found=[]
        for p in files:
            n=p.name
            if n.startswith(t['plan']+'[') and (not t['region'] or f'[{t["region"]}]' in n):found.append(p)
        if not found:continue
        p=found[0]; data=p.read_bytes(); e=p.suffix.lower(); h,rel=save_doc(data,e,{'type':'official_2028_plan','university':t['canonical'],'year':2028,'source':'대입정보포털 어디가 공식 묶음','original_name':p.name})
        slots[(t['canonical'],2028)]={'university':t['canonical'],'year':2028,'source_type':'원본파일','url':'https://www.adiga.kr/','hash':h,'path':rel}
def add_adiga_2025_fallback(slots):
    folder=Path('output/official_results/2025')
    if not folder.exists():return
    texts=[]
    for p in folder.glob('*.pdf'):
        try:
            text='\n'.join((page.extract_text() or '') for page in PdfReader(str(p)).pages)
            texts.append((p,text))
        except Exception:pass
    aliases={'KAIST':'한국과학기술원','GIST':'광주과학기술원','DGIST':'대구경북과학기술원','UNIST':'울산과학기술원','POSTECH':'포항공과대학교'}
    for t in TARGETS:
        key=(t['canonical'],2025)
        if key in slots:continue
        name=aliases.get(t['canonical'],re.sub(r' (서울|ERICA|죽전|고양|메트로폴|동두천|인천|세종|미래|글로컬|천안|WISE)캠퍼스$','',t['canonical']))
        for p,text in texts:
            if name in text:
                data=p.read_bytes(); h,rel=save_doc(data,'.pdf',{'type':'official_public_compilation','university':t['canonical'],'year':2025,'source':'대입정보포털 어디가','original_name':p.name})
                slots[key]={'university':t['canonical'],'year':2025,'source_type':'공식공공기관대체자료','url':'https://www.adiga.kr/','hash':h,'path':rel}; break

def main():
    slots={}; add_plan_slots(slots)
    tasks=[]
    with ThreadPoolExecutor(max_workers=24) as ex:
        for t in TARGETS:
            for y in YEARS: tasks.append(ex.submit(collect_slot,t,y))
        done=0
        for f in as_completed(tasks):
            done+=1
            try:r=f.result()
            except Exception:r=None
            if r:
                u,y,z=r; slots[(u,y)]={'university':u,'year':y,**z}
            if done%50==0:print(json.dumps({'processed':done,'slots':len(slots)},ensure_ascii=False),flush=True)
    add_adiga_2025_fallback(slots)
    ranked=sorted(slots.values(),key=lambda x:(0 if x['source_type']=='원본파일' else 1,x['year']!=2028,x['university'],x['year']))
    selected=ranked[:500]
    rows=[]
    for i,s in enumerate(selected,1):
        d=SLOTS/safe(s['university']); d.mkdir(parents=True,exist_ok=True)
        ptr=d/f"{s['year']}.txt"; ptr.write_text('\n'.join([f"관리번호: SLOT-{i:03d}",f"대학: {s['university']}",f"학년도: {s['year']}",f"출처유형: {s['source_type']}",f"공식URL: {s.get('url','')}",f"직접URL: {s.get('direct_url','')}",f"보존문서: {s['path']}",f"SHA256: {s['hash']}"]),encoding='utf-8')
        rows.append({'id':f'SLOT-{i:03d}','university':s['university'],'year':s['year'],'source_type':s['source_type'],'official_url':s.get('url',''),'direct_url':s.get('direct_url',''),'document_path':s['path'],'sha256':s['hash'],'pointer':ptr.relative_to(FINAL).as_posix()})
    with (FINAL/'slot_manifest.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['id']); w.writeheader(); w.writerows(rows)
    summary={'target_slots':784,'selected_slots':len(rows),'unique_slot_keys':len({(r['university'],r['year']) for r in rows}),'2028_slots':sum(r['year']==2028 for r in rows),'result_slots':sum(r['year']!=2028 for r in rows),'original_file_slots':sum(r['source_type']=='원본파일' for r in rows),'webpage_slots':sum(r['source_type']=='공식웹페이지보존본' for r in rows),'public_fallback_slots':sum(r['source_type']=='공식공공기관대체자료' for r in rows),'unique_documents':len({r['sha256'] for r in rows})}
    (FINAL/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(summary,ensure_ascii=False,indent=2))
    if len(rows)<500:return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
