import urllib.request,json,hashlib,datetime
from pathlib import Path
out=Path('artifacts/reports/s5-04-xgboost-feasibility-v1'); url='https://pypi.org/pypi/xgboost-cpu/3.4.1/json'
try:
 with urllib.request.urlopen(url,timeout=15) as r: j=json.load(r)
 f=next(x for x in j['urls'] if x['filename']=='xgboost_cpu-3.4.1-py3-none-win_amd64.whl')
 with urllib.request.urlopen(f['url'],timeout=45) as r: data=r.read()
 digest=hashlib.sha256(data).hexdigest(); assert digest==f['digests']['sha256'];(out/f['filename']).write_bytes(data)
 result={'status':'pass','metadata_url':url,'download_url':f['url'],'filename':f['filename'],'bytes':len(data),'sha256':digest,'pypi_sha256':f['digests']['sha256'],'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
except Exception as e: result={'status':'failed','error':repr(e),'metadata_url':url}
(out/'wheel-download.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(result)
