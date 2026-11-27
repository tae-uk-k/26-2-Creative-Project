"""Evidence-linked partial coding. These rows do not create the measurement cohort."""
import csv
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'analysis'/'재접근_상세검수_20261103_01'
with (DEST/'상세_근거목록.csv').open(encoding='utf-8-sig',newline='') as f:
    records=list(csv.DictReader(f))

def evidence(sid,platform,section):
    return next(r for r in reversed(records) if (r['store_id'],r['platform'],r['section'])==(sid,platform,section))

specs=[
 ('MD-10372376',1,1,'kakao','menu','피자아이풍기\n\n22,000원',
  ''),
 ('MD-10372376',2,2,'kakao','menu_photo_bundle','IN ANY OF THE FOLLOWING SAUCES',
  ''),
 ('MD-10372376',3,1,'kakao','home_hours','02-777-2580',
  ''),
 ('MD-7872029',1,1,'kakao','menu','로스가스\n\n15,000원',
  ''),
 ('MD-7872029',2,2,'official','official_primary_menu','양배추, 밥, 미소장국 필요하신대로 계속 서비스 해드립니다.',
  ''),
 ('MD-7872029',3,1,'kakao','home_hours','15:00 ~ 17:00 브레이크타임',
  ''),
]
# Korean wording is kept explicit in the review table below.
reasons=[
 '등록 텍스트 8개와 사진 5장을 확인했다. 메뉴·가격은 연결되지만 인원·개수 등의 판매 단위는 일부 암묵적이다. 사진의 SOLD OUT은 촬영 시 표기이며 현재 제공 여부로 확정하지 않았다.',
 '사진 메뉴판에서 파스타 종류와 소스를 선택하도록 연결한다. 단순한 맛 소개와 구분한다. 실제 열람한 이미지 2e35d631ede907c4가 근거다.',
 'Google 전화는 02-777-2579, 카카오는 02-777-2580이다. 같은 주소의 다른 대표번호일 가능성도 미해결로 병기하며, 어느 번호가 틀렸다고 확정하지 않았다.',
 '텍스트 6개와 최신 쪽 사진 3장에서 메뉴·가격을 확인했다. 사진의 접시 단위는 암묵적이며 인원·중량의 완전한 표기로 보지 않았다. 나머지 사진 27장은 저장만 했고 읽었다고 기록하지 않았다.',
 '공식 로스가스 상세에서 리필 대상과 제공 조건을 확인했다. 지도 텍스트만 보고 조건 미흡으로 분류하지 않았다.',
 '카카오는 토·일 15–17시 휴게를 표시한다. Google과 공식은 매일 11–21시이며 휴게 안내를 확인하지 못했다. 부분적인 채널 차이로 1점이며, 외곽 영업시간·전화·주소는 일치한다.',
]
rows=[]
for idx,(sid,item,score,platform,section,quote,_) in enumerate(specs):
    source=evidence(sid,platform,section)
    if section!='menu_photo_bundle':
        body=json.loads((ROOT/source['evidence_file']).read_text(encoding='utf-8'))['body']
        assert quote in body, (sid,item,'quote mismatch')
    others=[]
    if item==3:
        others.append(evidence(sid,'google','overview_hours')['evidence_file'])
    if sid=='MD-7872029' and item==3:
        others.append(evidence(sid,'official','official_home')['evidence_file'])
    if sid=='MD-10372376' and item==2:
        others.append(str((DEST/'menu_photos'/'MD-10372376_2e35d631ede907c4.jpg').relative_to(ROOT)))
    rows.append(dict(store_id=sid,item=item,score=score,status='reviewed_not_selected',quote=quote,
        source_url=source['source_url'],observed_at=source['observed_at'],evidence_file=source['evidence_file'],
        comparison_evidence=';'.join(others),reason=reasons[idx],
        writer_status='official' if platform=='official' else 'mixed_or_not_verified',
        primary_analysis_included=False))
with (DEST/'GEO_항목별점수_부분검수.csv').open('x',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,list(rows[0]));writer.writeheader();writer.writerows(rows)
with (DEST/'부분검수_제외판정.json').open('x',encoding='utf-8') as f:
    json.dump([dict(store_id=sid,total=4,group=None,included=False,
        reason='사전 기준의 4점 제외. 0–3점 또는 5–6점으로 임의 변경하지 않음')
        for sid in ['MD-10372376','MD-7872029']],f,ensure_ascii=False,indent=2)
print(json.dumps(dict(reviewed_item_rows=len(rows),score_4_exclusions=2,finalized_pairs=0),ensure_ascii=False))
