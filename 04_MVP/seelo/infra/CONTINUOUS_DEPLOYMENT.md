# seelo 자동 배포

2026-11-03부터 `.github/workflows/deploy-seelo.yml`을 사용한다.

## 실행 조건

- 운영 브랜치: `backend-0-13`.
- 해당 브랜치에 `04_MVP/seelo/**` 또는 배포 워크플로 변경을 push하면 실행한다.
- PostgreSQL 테스트 DB에서 ruff·OpenAPI 계약·백엔드 테스트 전체(쇼핑몰 브라우저 실행기의 로컬 HTML·Chromium 시험 포함)가 통과해야 한다. 실제 공급자 키가 필요한 live 테스트는 별도다.
- 프런트는 Node 22.16 컨테이너에서 형식·타입·시험·빌드를 실행하고, 요청 계약 검사와 `frontend/Dockerfile` 이미지 빌드까지 통과해야 한다. (2026-11-25 추가. 2026-11-28 실행 46074117212에서 처음 통과했다.)
- 배포 작업은 한 번에 하나만 실행한다. GitHub Actions 실행 화면에서 결과와 실패 단계를 확인한다.

## 피그마 제출용 고정 주소

- 제출·공유 주소: `https://seelo.site/prototype`.
- 별도 화면이나 클릭 없이 현재 피그마 프로토타입으로 HTTP 302 자동 이동한다. `/prototype/`도 같은 목적지로 이동한다.
- `Cache-Control: no-store`로 이전 목적지가 캐시에 남지 않게 한다. 요청 쿼리로 이동 목적지를 바꿀 수 없다.
- 피그마 링크가 바뀌면 `infra/nginx/prototype.conf`의 `return 302` 목적지만 수정해 `backend-0-13`에 push한다. 자동 배포가 완료되면 기존 제출 주소로 새 피그마가 열린다.
- 2026-11-28 쇼핑몰 화면 배포부터 첫 화면은 쇼핑몰 랜딩이다. 고정 주소는 그대로 유지한다. CI에서 nginx 구문을 검사하고, 배포 뒤 `check-web.py`로 실제 HTTPS 이동·캐시 정책을 확인한다.

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
4. DB 백업 후 커밋별 `/opt/seelo/releases/git-<SHA>-<시각>`에 배치한다. 백엔드 이미지와 프런트 화면 이미지(`seelo-web:git-<SHA>`)를 빌드한다. 운영 env에 `SEELO_BROWSER_WORKER=true`가 있으면 Playwright 이미지(`seelo-backend-fix`)도 빌드하고 `worker-fix`를 함께 올린다. `deployment.json`은 `infra/nginx/meta`에 쓴다.
5. 운영 환경의 이미지 태그와 `/opt/seelo/current`를 변경하고 API·메일 제외 기본 워커·AI 워커·nginx를 갱신한다. DB 컨테이너/볼륨은 교체하지 않는다.
6. Docker readiness, 실제 HTTPS API/DB health, `/deployment.json`의 커밋 ID를 검증한다. 실패하면 운영 환경 파일과 current를 함께 이전 값으로 복원하고 이전 서비스를 올린다.
7. GitHub에서 `infra/scripts/check-web.py --secure-cookie`로 첫 화면·직접 경로 새로고침·정적 파일·없는 파일 404·API 프록시·CSRF 쿠키·배포 커밋을 확인한다. 기존 `/prototype`은 고정 주소 이동과 캐시 정책을 함께 검사한다. 같은 스크립트를 로컬 Docker 검증에도 쓴다. 실패 시 브라우저 워커만 새로 올린 경우에는 이전 서비스를 올린 뒤 `worker-fix`를 멈춘다.

배포 로그는 VM `/var/log/seelo-deploy/`의 root 전용 파일에 남는다. 이전 설정·이미지·백업·실패한 후보 파일은 삭제하지 않는다. DB migration은 별도 검토·실행 뒤 다시 배포한다.

프런트 이미지는 운영 env의 `VITE_SEELO_MANAGER_NAME`·`VITE_SEELO_MANAGER_PHONE`만 빌드 인자로 받는다(2026-11-28). 값이 비면 스마트스토어 위임 안내의 복사 버튼을 숨긴다. 값을 바꾸면 다시 배포해야 화면에 반영된다.

## 운영 DB 마이그레이션 수동 적용

새 migration이 있는 커밋은 자동 배포가 `schema_check` 단계에서 멈춘다. 이 단계에서는 운영 서비스를 바꾸지 않는다. 실패한 실행이 VM에 올린 패키지로 아래를 진행한 뒤, GitHub에서 같은 실행의 실패 작업을 다시 실행한다.

```sh
SHA=<배포할 커밋 40자리>
SRC=$(ls -d /home/ubuntu/seelo-ci/$SHA-* | tail -1)/source.tar.gz
WORK=/opt/seelo/migrate/git-$SHA
sudo mkdir -p "$WORK" && sudo tar -xzf "$SRC" -C "$WORK"
# 1. 백업(배포기와 같은 스크립트·경로)
sudo env SEELO_ENV_FILE=/etc/seelo/production.env BACKUP_DIR=/var/backups/seelo sh /opt/seelo/current/infra/scripts/backup.sh
# 2. 새 백엔드 이미지로 migrate만 실행한다. 실행 중인 API·워커는 그대로 둔다.
cd "$WORK"
sudo docker build -t seelo-backend:git-$SHA backend
sudo env SEELO_IMAGE_TAG=git-$SHA docker compose --env-file /etc/seelo/production.env -f docker-compose.prod.yml run --rm --no-deps migrate
# 3. 확인(쇼핑몰 기준 0004_commerce_measure)
sudo docker compose --env-file /etc/seelo/production.env -f /opt/seelo/current/docker-compose.prod.yml exec -T db psql -U seelo -d seelo -tAc 'select version_num from alembic_version'
```

쇼핑몰 migration(0002~0004)은 테이블·제약 추가만 한다. 기존 지도 테이블과 데이터는 바꾸지 않는다. 로컬 개발 DB(0001, 지도 데이터 있음)에서 2026-11-28에 같은 순서로 적용을 확인했다.

2026-11-28 운영 적용 기록: 커밋 `bdc7f2a` 첫 실행이 `schema_check`에서 멈췄다. 위 절차로 백업 `seelo_20261127T221131Z.dump`를 만들고, 패키지의 migration 파일 해시를 커밋과 대조한 뒤 `0001_initial` → `0004_commerce_measure`를 적용했다. 같은 실행의 배포 작업을 다시 실행해 배포와 외부 HTTPS 확인이 통과했다. 이때부터 첫 화면은 쇼핑몰 랜딩이다.

사이트: https://seelo.site/ · 배포 커밋 확인: https://seelo.site/deployment.json

AI의 PC CLI 연결은 자동 배포와 별개다. PC가 꺼져도 GitHub에서 서버 배포는 실행되며, PC CLI를 쓰는 AI 요청은 PC 연결이 필요하다.
