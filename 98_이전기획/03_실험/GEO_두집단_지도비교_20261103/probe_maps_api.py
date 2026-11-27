"""Read-only official-map API availability, with a non-restaurant calibration query."""
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ENV=Path(r'C:\Users\xodnr\AppData\Local\seelo\secrets\gcp-production.env')

def credentials():
    values={}
    for line in ENV.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.startswith('#'):
            key,value=line.split('=',1)
            if key.strip() in ['GOOGLE_PLACES_API_KEY','KAKAO_REST_API_KEY']:
                values[key.strip()]=value.strip().strip('"').strip("'")
    return values

def main():
    keys=credentials();results=[]
    requests=[('google',urllib.request.Request('https://places.googleapis.com/v1/places:searchText',
       data=json.dumps({'textQuery':'서울특별시청','languageCode':'ko','maxResultCount':1}).encode(),
       headers={'X-Goog-Api-Key':keys['GOOGLE_PLACES_API_KEY'],'X-Goog-FieldMask':'places.id,places.displayName,places.formattedAddress',
                'Content-Type':'application/json'})),
       ('kakao',urllib.request.Request('https://dapi.kakao.com/v2/local/search/keyword.json?'+urllib.parse.urlencode({'query':'서울특별시청','size':1}),
        headers={'Authorization':'KakaoAK '+keys['KAKAO_REST_API_KEY']}))]
    for platform,req in requests:
        try:
            with urllib.request.urlopen(req,timeout=25) as r: status=r.status;data=json.loads(r.read().decode())
        except urllib.error.HTTPError as e:status=e.code;data=json.loads(e.read().decode())
        except Exception as e:status='error';data={'exception_type':type(e).__name__}
        record={'platform':platform,'checked_at_utc':datetime.now(timezone.utc).isoformat(),'http_status':status,'public_response':data}
        results.append(record);print(json.dumps({'platform':platform,'http_status':status}))
    path=ROOT/'readiness'/'official_map_api_probe.json'
    if path.exists():raise RuntimeError('Existing probe preserved; use a new timestamped file')
    path.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
