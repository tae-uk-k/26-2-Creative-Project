"""Google 비즈니스 프로필 관리 화면(business.google.com) 조작(09 8.4, GOOGLE_FIX_MODE=browser).

셀렉터는 selectors/google.yaml([PoC]). 영업시간·메뉴·편의 정보처럼 입력이 복잡한 칸은 실제 화면을 본 뒤
칸별 함수(_write_hours 등)로 더한다. 그 전에는 ScreenAdmin이 FieldWriteFailed로 넘긴다(수동 처리).
"""

from seelo.integrations.browser.screen import ScreenAdmin


class GoogleAdminBrowser(ScreenAdmin):
    pass
