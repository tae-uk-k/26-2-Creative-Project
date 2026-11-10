# seelo 자동 배포

2026-11-03부터 `.github/workflows/deploy-seelo.yml`을 사용한다.

## 실행 조건

- 운영 브랜치: `backend-0-13`.
- 해당 브랜치에 `04_MVP/seelo/**` 또는 배포 워크플로 변경을 push하면 실행한다.
- PostgreSQL 테스트 DB에서 ruff·OpenAPI 계약·테스트 전체가 통과해야 배포 작업이 시작된다. 실제 공급자 키가 필요한 live 테스트는 별도다.
- 배포 작업은 한 번에 하나만 실행한다. GitHub Actions 실행 화면에서 결과와 실패 단계를 확인한다.

## 피그마 제출용 고정 주소

- 제출·공유 주소: `https://seelo.site/prototype`.
- 별도 화면이나 클릭 없이 현재 피그마 프로토타입으로 HTTP 302 자동 이동한다. `/prototype/`도 같은 목적지로 이동한다.
- `Cache-Control: no-store`로 이전 목적지가 캐시에 남지 않게 한다. 요청 쿼리로 이동 목적지를 바꿀 수 없다.
- 피그마 링크가 바뀌면 `infra/nginx/prototype.conf`의 `return 302` 목적지만 수정해 `backend-0-13`에 push한다. 자동 배포가 완료되면 기존 제출 주소로 새 피그마가 열린다.
- 첫 화면의 “피그마 프로토타입” 버튼도 이 고정 주소를 사용한다. CI에서 nginx 구문과 실제 HTTPS GET·HEAD 이동을 확인한다.

## 인증·접속

- Google Workload Identity Federation으로 GitHub의 단기 인증을 사용한다. 서비스 계정 JSON 키·PC SSH 개인키는 GitHub에 등록하지 않는다.
- Google의 신뢰 조건은 저장소 ID `1370972740`, 소유자 ID `110802129`, 운영 브랜치, 이 워크플로 파일 경로를 모두 제한한다.
- 서비스 계정은 `seelo-github-deploy@seelo-prod-20261030.iam.gserviceaccount.com`이다. 읽기용 사용자 지정 역할과 `seelo-prod` 한 대의 metadata 변경 권한만 부여한다. 프로젝트 전체 SSH 키 변경 권한은 없다.
- IAP 접속 권한은 내부 IP `10.42.0.2`의 TCP 22로 제한한다. 방화벽 `seelo-allow-iap-ssh`는 `seelo-iap-ssh` 태그에 Google IAP 원본 `35.235.240.0/20`만 허용한다. 기존 공개 SSH 허용 범위는 넓히지 않았다.
- CI 실행마다 생성한 SSH 공개키를 해당 VM에만 30분 유효기간으로 추가한다. 기존 metadata와 SSH 키는 유지한다. 서버 ED25519 호스트 키를 고정해 검증한다.
- GitHub repository variables: `SEELO_WIF_PROVIDER`, `SEELO_SSH_HOST_KEY`. 둘 다 식별자/공개키다.

## 서버 반영

1. `git archive`로 해당 커밋의 seelo 디렉터리를 패키징하고 SHA-256을 계산한다.
2. IAP/SSH로 VM에 전달한다. GCP VM에서 Docker 이미지를 빌드하므로 이미지 레지스트리 로그인은 필요 없다.
3. 안전한 아카이브 경로와 현재 DB revision을 확인한다. 새 migration이 있으면 자동 적용하지 않고 배포를 중단한다.
4. DB 백업 후 커밋별 `/opt/seelo/releases/git-<SHA>-<시각>`에 배치한다.
5. 운영 환경의 이미지 태그와 `/opt/seelo/current`를 변경하고 API·메일 제외 기본 워커·AI 워커·nginx를 갱신한다. DB 컨테이너/볼륨은 교체하지 않는다.
6. Docker readiness, 실제 HTTPS API/DB health, `/deployment.json`의 커밋 ID를 검증한다. 실패하면 운영 환경 파일과 current를 함께 이전 값으로 복원하고 이전 서비스를 올린다.
7. GitHub에서도 실제 첫 화면의 “피그마 프로토타입” 링크와 HTTPS/DB/배포 커밋을 재확인한다.

배포 로그는 VM `/var/log/seelo-deploy/`의 root 전용 파일에 남는다. 이전 설정·이미지·백업·실패한 후보 파일은 삭제하지 않는다. DB migration은 별도 검토·실행 뒤 다시 배포한다.

사이트: https://seelo.site/ · 배포 커밋 확인: https://seelo.site/deployment.json

AI의 PC CLI 연결은 자동 배포와 별개다. PC가 꺼져도 GitHub에서 서버 배포는 실행되며, PC CLI를 쓰는 AI 요청은 PC 연결이 필요하다.
