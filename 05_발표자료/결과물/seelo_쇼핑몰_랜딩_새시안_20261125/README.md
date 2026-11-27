# seelo 쇼핑몰 랜딩 새 시안

- [밝은 첫 화면](index.html)
- [어두운 첫 화면](dark.html)
- [쇼핑몰 이미지 3종](images.html)

seelo 화면은 스마트스토어·카페24 상품 담당자가 승인한 상세 설명을 반영하는 흐름으로 설계했다. [프로젝트 기획](../../../01_기획/개발/쇼핑몰_관리자화면자동화.md)

울 혼방 니트의 혼용률과 판매가는 정비 화면을 설명하기 위한 예시다. 첨부 이미지의 AI 검색 질문과 서비스 이름을 반영했다. 서비스 이름은 AI 검색 예시로 표시했다.

## 2026-11-27 하단 구성

두 시안 모두 첫 문구는 “AI 검색에서 우리 상품이 답이 되도록”이다. 하단은 AI 쇼핑 대화, AI에 검색을 맡기는 쇼핑, SEO·GEO 비교, seelo 이용 과정 순서다. 데스크톱에서는 설명과 예시를 나란히 두고, 모바일에서는 위아래로 배치한다.

이용 과정은 정비 전 노출 측정, 판매자가 승인한 상품 정보 반영, 일정 기간 후 재측정과 전후 비교 보고서로 구성했다.

## 이미지 제작

세 이미지 모두 내장 ImageGen으로 생성했다. 웹에서 쓸 수 있도록 WebP로 저장했다.

| 이미지 | 생성 지시문 요약 |
| --- | --- |
| [겹쳐 놓은 쇼핑몰](assets/stores-layered.webp) | 어두운 흑록색 배경의 오른쪽에 리빙·신발·뷰티·디지털·캠핑 쇼핑몰 창 다섯 개를 겹친다. 왼쪽은 제목을 위한 여백으로 비운다. |
| [정면 갤러리](assets/stores-wall.webp) | 서로 다른 여섯 쇼핑몰을 정면 3열×2행으로 배치한다. 개별 창에 상품 목록과 브라우저 표시를 넣는다. |
| [밝은 전시형](assets/stores-studio.webp) | 밝은 아이보리 배경에서 쇼핑몰 창 네 개가 서로 겹치고 떠 있는 듯 배치한다. 부드러운 빛과 그림자를 사용한다. |

모든 이미지에 인물과 문구를 넣지 않도록 지정했다.


## 비교표·플랫폼 로고

- 첨부 자료의 SEO·GEO 비교 다섯 항목을 HTML 표로 옮겼다. 검색 결과와 AI 답변에서 정보를 찾고 비교하는 방식에 초점을 맞췄다. [GEO 원 논문](https://arxiv.org/abs/2311.09735) · [Google 검색 AI 기능 문서](https://developers.google.com/search/docs/appearance/ai-features)
- 네이버 스마트스토어는 판매자센터 아이콘, 카페24는 회사 사이트의 워드마크를 사용했다. [네이버 브랜드 가이드](https://apicenter.commerce.naver.com/docs/solution-doc/3000/브랜드-가이드) · [카페24 워드마크 원본](https://img.cafe24.com/images/common/cafe24.svg)

## 2026-11-26 디자인 수정

첫 화면에 쇼핑몰 이미지를 크게 배치하고, 그 아래에 “ChatGPT가 추천하는 상품, 사장님 상품도 있을까요?”와 정비 예시 버튼을 배치했다. 하단에서 AI 쇼핑 질문, 상품 설명 전후, 이용 절차, SEO·GEO 비교와 지원 쇼핑몰을 차례로 보여준다. [MacBook Air](https://www.apple.com/kr/macbook-air/) · [AirPods Pro](https://www.apple.com/kr/airpods-pro/)

`apple-design`으로 제목·본문·라벨의 위계를 정리했다. `impeccable`로 채팅창 장식, 겹친 카드, 반복 이미지와 강조를 줄였다. [Impeccable](https://github.com/pbakaus/impeccable)
