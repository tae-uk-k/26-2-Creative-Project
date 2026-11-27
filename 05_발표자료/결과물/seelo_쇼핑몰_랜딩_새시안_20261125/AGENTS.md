# 랜딩페이지 수정 규칙

- 사용자가 정한 문구는 공백과 줄바꿈만 화면에 맞게 처리한다. 단어, 조사, 문장부호, 정보 순서는 사용자가 변경을 지시한 곳만 바꾼다.
- 한 문장을 같은 크기와 굵기로 쓰라는 지시는 문장 전체에 적용한다. 제목의 일부를 별도 제목, 작은 라벨, 강조용 서체로 분리하지 않는다. 줄바꿈은 같은 서체로 처리한다.
- 참고 이미지 지시는 사용자가 지정한 요소에 적용한다. 이미지와 기존 화면에서 유지할 요소를 먼저 확인한다. 지시받지 않은 제목, 라벨, 예시 답변, 플랫폼 이름을 추가하지 않는다.
- 수정 대상 시안과 구간을 먼저 특정한다. 공통 스타일 변경 전에 다른 시안에도 수정이 필요한지 확인한다. 스타일 스킬의 일반 규칙은 사용자가 지정한 문구와 구도보다 우선하지 않는다.
- 토스 디자인 시스템을 선택한 시안은 이후 수정과 추가 요소에도 토스 디자인 시스템을 계속 적용한다. `toss-design-system` 스킬에서 해당 요소의 색상과 글자 위계, 간격, 컴포넌트 상태를 확인하고 기존 시안과 맞춘다. 각 시안은 사용자가 선택한 디자인 시스템을 따른다.
- 어두운 시안의 문구, 제목 위계, 대화창, 하단 배치를 바꿀 때는 `checks/dark-landing.js`를 실행한다. 검사 속 문구와 기준은 사용자 지시가 변경된 경우에만 함께 갱신한다. 데스크톱과 모바일 화면을 캡처해 참고 이미지와 대조한다.

## 브라우저 검사

이 폴더에서 다음 명령을 실행한다. 검사 파일은 열린 `dark.html`을 1440·1024·768·390·320px에서 확인한다.

```powershell
$darkPageUri = [Uri]::new((Resolve-Path './dark.html').Path).AbsoluteUri
npm exec --yes --package=@playwright/cli@0.1.25 -- playwright-cli -s=seelo-dark-check open
npm exec --yes --package=@playwright/cli@0.1.25 -- playwright-cli -s=seelo-dark-check run-code "async page => { await page.goto('$darkPageUri'); }"
npm exec --yes --package=@playwright/cli@0.1.25 -- playwright-cli -s=seelo-dark-check run-code --filename checks/dark-landing.js
npm exec --yes --package=@playwright/cli@0.1.25 -- playwright-cli -s=seelo-dark-check close
```
