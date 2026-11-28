"""카카오 파트너센터(매장 > 매장정보) 조작(09 8.4, KAKAO_FIX_ENABLED=true일 때만).

셀렉터는 selectors/kakao.yaml([PoC]). 영업시간·가격 정보·링크·서비스·태그는 실제 화면을 본 뒤
칸별 함수로 더한다. 그 전에는 ScreenAdmin이 FieldWriteFailed로 넘긴다(수동 처리).
"""

from seelo.integrations.browser.screen import ScreenAdmin


class KakaoPartnerBrowser(ScreenAdmin):
    pass
