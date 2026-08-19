import requests
from urllib.parse import quote_plus
q='site:admission.cau.ac.kr 2020학년도 입시결과 중앙대학교'
u='https://www.bing.com/search?q='+quote_plus(q)+'&format=rss'
r=requests.get(u,timeout=20,headers={'User-Agent':'Mozilla/5.0'})
print(r.status_code, r.headers.get('content-type'), len(r.content))
print(r.text[:2000])
