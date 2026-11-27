"""Neutral exact-URL access diagnostic. Not a recommendation measurement."""
import json
import study

if __name__ == '__main__':
    config = json.loads((study.ROOT / '고정_실행설정.json').read_text(encoding='utf-8'))
    cell = {
        'cell_id': 'NEUTRAL-EXACT-DETAIL',
        'prompt': '다음 두 공개 지도 상세 URL을 각각 직접 열어 서울특별시청의 주소와 실제 본문에서 확인한 문구를 알려줘. '
                  '열지 못한 지도는 접근 실패라고 명시하고 추측하지 마. '
                  'https://place.map.kakao.com/8430129 '
                  'https://www.google.com/maps/place/서울특별시청/data=!3m1!4b1!4m4!3m3!1s0x357ca2f332cb082b:0xe92b70ac420cf0a8!16s%2Fm%2F03ylsqy!20s8Q98HX8H%2BJ7P?hl=ko',
    }
    print(json.dumps(study.run_one(config, cell, readiness=True), ensure_ascii=False), flush=True)
