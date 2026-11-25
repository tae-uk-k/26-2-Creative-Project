# 배포 메타 정보

배포 스크립트가 이 폴더에 `deployment.json`(배포 커밋·시각)을 쓴다. nginx는 `/deployment.json` 요청만 이 폴더에서 제공한다. 화면 정적 파일은 `frontend/Dockerfile`로 만든 `seelo-web` 이미지에 들어 있다.
