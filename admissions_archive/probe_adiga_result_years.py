from __future__ import annotations
import json,re,requests
from bs4 import BeautifulSoup
PAGE='https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do'
AJAX='https://www.adiga.kr/uct/acd/ade/criteriaAndResultItemNewAjax.do'
s=requests.Session();s.headers.update({'User-Agent':'Mozilla/5.0','Accept-Language':'ko-KR,ko;q=0.9'})
rows=[]
for search_year in range(2021,2028):
  page_url=f'{PAGE}?menuId=PCUVTINF2000&searchSyr={search_year}&unvCd=0000063'
  p=s.get(page_url,timeout=40)
  for code in ('20','30','40'):
    r=s.post(AJAX,data={'searchSyr':str(search_year),'unvCd':'0000063','tsrdCmphSlcnArtclUpCd':code,'compUnvCd':''},headers={'Referer':page_url,'X-Requested-With':'XMLHttpRequest'},timeout=40)
    soup=BeautifulSoup(r.text,'html.parser'); plain=re.sub(r'\s+',' ',soup.get_text(' ',strip=True))
    rows.append({'search_year':search_year,'result_year':search_year-1,'code':code,'status':r.status_code,'bytes':len(r.content),'blocks':len(soup.select('.tbAdmRes')),'tables':len(soup.find_all('table')),'competition':'경쟁률' in plain,'cut70':'70%' in plain,'snippet':plain[:120]})
print(json.dumps(rows,ensure_ascii=False,indent=2))
