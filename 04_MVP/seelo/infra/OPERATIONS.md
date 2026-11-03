# seelo 운영 준비·검증(16단계, W-11)

2026-11-03 자동 배포 구성은 [자동 배포 운영 문서](CONTINUOUS_DEPLOYMENT.md)를 따른다. 아래 날짜별 검증 기록과 구분한다.

2026-10-31 GCP에 API·PostgreSQL·nginx와 메일을 제외한 워커를 배포했다. 실제 도메인 HTTPS, 지도 검색, Google·카카오 인증 콜백, 서버→PC Codex CLI 웹 검색을 검증했다. 매일 KST 04:00 백업·PC 외부 보관·별도 DB 복구와 PC 기준 5분 외부 health 감시를 가동했다. 승인한 시험 메일 10통은 SMTP가 수락했으며 받은편지함 수신은 미확인이다. Gemini 인증·최종 가입 화면/세션·카카오 웹훅 등록·알림 도착·실제 가게 인수는 미완료다. 아래 초기 준비 절차와 현재 운영의 차이는 마지막 '현재 로컬 CLI 운영' 절을 따른다. 실제 증거와 남은 항목은 [GCP 구축 기록](../../../03_실험/구현시험/seelo_GCP_구축기록_20261030.md)에 기록한다. React 화면은 이번 작업 범위에 포함되지 않아 웹 루트는 기존 자리 표시 화면이다.

## 1. 운영 설정

- `docker-compose.prod.yml`은 **독립 파일**이다. 개발 `docker-compose.yml`과 `-f`로 합치지 않는다. 프로젝트 이름도 `seelo-prod`로 분리했다.
- `infra/production.env.example`를 저장소 밖 개인 경로에 복사하고 모든 빈 값을 채운다. `SEELO_ENV_FILE`과 `--env-file`은 같은 절대 경로다. Linux에서는 읽기 권한을 소유자에게만 준다. DB URL 비밀번호는 URL 인코딩하고 `POSTGRES_PASSWORD`와 맞춘다. 운영 DB·큐 호스트는 `db:5432`, 사용자·DB는 `seelo`다.
- `PUBLIC_HOST`는 실제 도메인만(스킴·경로 없음). `SEELO_PROXY_SUBNET`은 다른 네트워크와 겹치지 않는 전용 서브넷을 운영자가 정한다. API는 이 프록시 대역만 신뢰한다.
- `APP_ENV=prod`, `COOKIE_SECURE=true`, `FAKE_EXTERNALS=false`, HTTPS는 Compose에서 고정한다. 운영 앱은 문서·OpenAPI를 공개하지 않는다(기존 `main.py`).
- 외부 포트는 web의 80·443만 있다. DB·API·워커·Mailpit의 호스트 포트는 없다. Mailpit 서비스도 없다.
- 워커 종료 대기 60초보다 긴 `stop_grace_period=75s`, API·DB healthcheck, 크기 제한이 있는 컨테이너 로그를 둔다.
- `AUTO_FIX_ENABLED=false`가 기본이다. 실제 셀렉터·권한 PoC가 끝나기 전에는 켜지 않는다. 켤 때는 `--profile fix` 워커도 필요하다.
- `SECRET_KEY`·`EMAIL_HMAC_KEY`·Fernet 키는 새로 만든다. 실제 비밀 값·인증서·DB 덤프를 Git에 넣지 않는다. 이메일 HMAC 키를 바꾸면 무료 사용 이력을 같은 이메일과 연결할 수 없으므로 보관한다.

검사·실행 예시(경로는 운영자가 실제 파일로 바꾼다):

```sh
docker compose --env-file /실제/운영.env -f docker-compose.prod.yml config --quiet
docker compose --env-file /실제/운영.env -f docker-compose.prod.yml build
docker compose --env-file /실제/운영.env -f docker-compose.prod.yml up -d
docker compose --env-file /실제/운영.env -f docker-compose.prod.yml ps
```

`migrate`가 DB 준비 뒤 Alembic·작업 큐 스키마를 적용하고, 끝난 뒤 API·워커가 시작된다. 코드·DB 변경 전 현재 백업·이전 이미지 태그를 확보한다. 롤백 때 DB 마이그레이션을 임의로 되돌리지 않는다. 재부팅·볼륨/DB 삭제 명령은 이 절차에 없다.

## 2. TLS

- `TLS_CERT_DIR`에 실제 도메인의 `fullchain.pem`·`privkey.pem`을 준비한다. 디렉터리를 web에 읽기 전용으로 연결한다. nginx가 `production.conf.template`의 `PUBLIC_HOST`만 치환한다.
- HTTP의 `/.well-known/acme-challenge/`는 인증서 검증용 webroot를 제공하고, 나머지는 HTTPS 308로 이동한다. `www`도 인증서에 포함하고 기본 도메인으로 308 이동한다. TLS 1.2·1.3, HSTS(1년), Referrer-Policy·nosniff·프레임 차단 헤더를 적용한다.
- 최초 발급은 `infra/nginx/acme-bootstrap.conf`를 사용하는 임시 HTTP nginx와 Certbot webroot 방식으로 진행한다. `ACME_WEBROOT_DIR` 기본값 `/var/lib/seelo/acme`를 호스트에 만들고, nginx에 `/var/www/acme:ro`로 연결한다. 발급 뒤 임시 컨테이너를 중지하고 운영 web을 시작한다. 영구 삭제·VM 재부팅은 하지 않는다.
- `infra/scripts/tls-deploy.sh`를 root 소유 실행 파일 `/usr/local/sbin/seelo-tls-deploy`로 설치한다. 기본 배포 경로는 `/opt/seelo/current`, 운영 환경 파일은 `/etc/seelo/production.env`다. 실제 인증서의 남은 유효 기간·호스트 이름·키 쌍을 검사하고 복사한다. 기존 파일은 별도 디렉터리에 보존하며 nginx 설정 검사가 실패하면 이전 파일을 복원한다. 설정 검사 성공 후에만 reload한다.
- `/etc/letsencrypt/renewal-hooks/deploy/seelo`에서 위 훅을 실행하고 `certbot.timer`를 확인한다. `certbot renew --cert-name seelo.site --dry-run --run-deploy-hooks --non-interactive --no-random-sleep-on-renew`로 실제 검증 경로와 reload를 시험한다. 셸 스크립트는 LF 줄바꿈으로 배포하며, SSH stdin으로 실행할 때 하위 Docker exec가 명령 스트림을 소비하지 않도록 한다.
- 접근 로그는 쿼리·Referer·User-Agent를 저장하지 않고 인증·재설정 경로의 토큰을 가린다. nginx 오류 로그는 요청 URI를 포함할 수 있어 `crit`만 `/dev/null`로 보낸다. 상세 장애는 API 구조화 로그·상태 코드·외부 감시로 확인한다. 시작 실패는 컨테이너 stderr·상태에서 확인한다.
- 로컬 `localhost`의 임시 인증서로 HTTPS health 200·헤더·HTTP 308·토큰 가림을 확인했다. **실제 도메인 인증서 검증·외부 접속 증거는 아니다.**

## 3. 백업·복구

- `infra/scripts/backup.sh`: `pg_dump -Fc --no-owner --no-acl`, `.partial`에 쓴 뒤 `pg_restore --list`가 성공해야 최종 `.dump`가 된다. 기존 파일은 덮어쓰지 않는다.
- `BACKUP_DIR`은 미리 연결한 **VM 밖 저장소**의 마운트 경로여야 한다. 디렉터리가 없으면 실패한다. 스크립트가 외부 저장소 연결·암호화·접근 정책을 대신하지 않는다.
- 매일 **KST 04:00**에 실행한다. 스케줄러가 UTC이면 매일 19:00 UTC다. 현재 장비의 시간대·스케줄러 설정은 바꾸지 않았다.
- 7일 지난 이 스크립트의 `seelo_YYYYMMDDTHHMMSSZ.dump`는 `BACKUP_DIR/quarantine/`으로 이동한다. 영구 삭제하지 않는다. 격리 대상을 확인한 뒤 운영자가 별도로 삭제를 승인·처리해야 하므로 전체 디스크 사용량은 7일치로 제한되지 않는다.
- `restore-check.sh dump파일 seelo_restore_새이름`: 아카이브 목록 확인 → **새 DB 생성** → 복구 → Alembic 버전·사용자 수 확인. 이미 있는 DB에는 실패한다. 운영 DB·검증 DB를 지우거나 덮어쓰지 않는다.
- 셸 환경에 `SEELO_ENV_FILE`, `BACKUP_DIR`을 설정해 실행한다. 비밀 파일을 shell `source`로 읽지 않고 Compose가 읽는다.
- 개발 확인 때만 `SEELO_COMPOSE_FILE`을 개발 compose 절대 경로로 바꿀 수 있다. 기본값은 운영 compose다. 백업·복구 확인 뒤 환경변수는 원래대로 돌린다.
- 로컬 확인: 개발 DB 백업을 **새 DB `seelo_restore_20261029_2117`**에 복구했다. Alembic `0001_initial`, users 30행 확인. 검증 DB는 보존했다. 외부 저장소·자동 스케줄은 미설정이다.

실행 예시(저장소 `04_MVP/seelo`에서, 실제 경로로 바꾼 뒤 실행):

```sh
SEELO_ENV_FILE=/실제/운영.env BACKUP_DIR=/실제/외부저장소 sh infra/scripts/backup.sh
SEELO_ENV_FILE=/실제/운영.env sh infra/scripts/restore-check.sh /실제/백업.dump seelo_restore_새이름
```

검증 DB 이름은 `seelo_restore_` 뒤에 영문·숫자·밑줄만 쓴다. 위의 `새이름`은 실제 사용 전 그 규칙에 맞게 바꾼다.

## 4. 감시

- 외부 모니터에서 `https://실제도메인/api/health`를 5분마다 확인한다. 서버 내부 감시만으로 VM 장애를 판단하지 않는다.
- `backend/scripts/check_uptime.py --url HTTPS주소`는 상태 200과 정확한 `{status: ok, db: ok}`를 검사한다. TLS 검증은 켜고 리디렉션·HTTP·인증 정보/쿼리가 든 URL은 거부한다. 결과는 `health=ok|failed|invalid_config`, 종료 코드 0·1·2다. 원문 URL·응답 본문·비밀 값은 출력하지 않는다.
- `SENTRY_DSN`을 채우면 기존 앱의 Sentry 오류 수집을 사용한다. 실제 수집·알림 수신은 별도 확인해야 한다.
- 실제 모니터·알림 대상은 아직 등록하지 않았다.

## 5. 배포 뒤 수동 인수 기록(W-11-2)

- [ ] VM·도메인·인증서·SMTP·외부 키·관리자 계정 준비.
- [ ] 실제 HTTPS 건강 확인·쿠키 Secure·문서 비공개·토큰 로그 가림. `SEELO_DEPLOY_BASE_URL` 설정 뒤 `uv run pytest -m live tests/live/test_e2e_deploy.py`는 이 선행 확인만 수행한다.
- [ ] 동의받은 가게로 가입·인증 → 식별·진단 → 신청·관리자 승인 → 초대·연결 확인 → 정비안 승인 → 정비 완료 → [지금 재측정] → 보고서·메일. ID·시각·비용·사용한 공급자를 기록한다.
- [ ] 외부 API 한 곳을 끈 상태에서 다른 출처/공급자·메일이 계속 동작하는지 확인. AI 한 공급자가 전부 실패하면 실패율 30%를 넘으므로 **측정 실패·보고서 미생성·무료 미차감이 올바른 결과**다. 성공으로 위장하지 않는다.
- [ ] 위 정상 시연을 **2번 연속** 성공한 기록. 실제 지도 쓰기는 승인·동의받은 칸만 한다.
- [ ] VM 밖 백업·복구 시험·7일 격리·5분 외부 감시·인증서 갱신·알림 도착 확인.

로컬 가짜 Compose·자동 테스트는 위 실제 배포 체크를 대신하지 않는다.

## 공식 참고(2026-10-29 확인)

- [Compose 운영 구성](https://docs.docker.com/compose/how-tos/production/), [서비스 종료 대기·healthcheck](https://docs.docker.com/reference/compose-file/services/)
- [nginx TLS 설정](https://nginx.org/en/docs/http/ngx_http_ssl_module.html)
- [PostgreSQL 16 pg_dump](https://www.postgresql.org/docs/16/app-pgdump.html), [pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html)

## 현재 로컬 CLI 운영(2026-10-31)

- 현재 구성은 `docker-compose.prod.yml` + `docker-compose.local-ai.yml`이다. 서버에서는 두 파일을 고정한 `sudo /usr/local/sbin/seelo-compose`를 사용한다. 일반 실행 예시를 그대로 사용해 overlay를 누락하지 않는다.
- `AI_BACKEND=local_cli`, Codex 모델 `codex-cli/gpt-6.1-sol`, 시험 반복 1회·공급자별 동시 1이다. API 키로 자동 대체하지 않는다. CLI의 구독/사용 한도와 API 청구액은 별개다. `DAILY_COST_LIMIT_USD=0`은 기존 API 측정 코드에서 **무제한**이며 호출 차단 값이 아니다.
- PC의 공식 Codex CLI를 기존 ChatGPT 인증으로 호출한다. SSH reverse Unix socket은 `/home/ubuntu/seelo-ai/bridge.sock`, 컨테이너에는 `/run/seelo-ai/bridge.sock`으로 읽기 전용 연결한다. PC 서버는 `127.0.0.1:18765`만 수신한다. 토큰·CLI 로그인 파일을 공개하지 않으며 CLI 로그인 파일은 GCP에 복사하지 않는다.
- PC 설정은 저장소 밖 `C:\Users\xodnr\AppData\Local\seelo\secrets\local-ai-bridge.env`, 실행 기록은 `C:\Users\xodnr\AppData\Local\seelo\local-ai`다. `supervisor`가 브리지와 SSH 연결을 복구하며 로그인 시작 폴더의 `seelo-local-ai-20261031.lnk`가 실행한다. 기존 프로세스·중복 실행은 확인하고 재사용한다. stale socket은 격리한다.
- PC가 꺼지거나 로그아웃/절전 상태이면 로컬 AI와 PC 감시는 중단된다. PC 전원·세션 설정은 바꾸지 않았다. 보안상 SSH가 현재 PC 공인 IP /32만 허용되므로 공인 IP 변경 시 재설정이 필요하다.
- 공식 Gemini CLI의 기존/최신 버전 모두 개인 로그인에서 `UNSUPPORTED_CLIENT/IneligibleTierError`로 차단됐다. 운영 `GEMINI_MEASURE_MODEL`은 빈 값이다. Gemini 큐 워커는 비설정 실행을 즉시 실패로 끝내는 용도로만 가동하며 외부 호출은 하지 않는다. 공급자 하나가 전부 실패하면 기존 30% 실패율 기준에 따라 진단 실패·무료 미차감이 정상이다. 두 공급자 정상 진단을 완료했다고 표시하지 않는다.
- 반복 횟수·질문 세트·API/CLI 전송 경로가 다른 전후 결과는 보고서 생성을 거부한다. 하나의 측정 안에 API와 CLI가 섞인 경우도 거부한다. 같은 CLI 경로로 만든 보고서에는 로컬 CLI 시험 안내를 붙인다.
- 기본 워커 큐는 `collect,measure,plan,report,periodic`이며 **email은 제외**한다. 2026-10-31 사용자 승인을 받은 한 주소의 시험 메일 10통만 별도 도구로 보냈고 SMTP 수락을 확인했다. 상태 기록으로 재실행 시 추가 발송하지 않는다. 받은편지함 도착·일반 메일 서비스 인수는 별도 확인이다.
- 매일 KST 04:00 `seelo-backup.timer`가 `/var/backups/seelo`에 검증 덤프를 만든다. 이 경로는 **VM 내부 스풀**이다. root export 도구를 통해 PC 보호 폴더 `secrets\backups`로 시간당 복사하고 SHA-256을 확인한다. 현재 3개가 외부에 보관됐고 최신 덤프는 새 DB `seelo_restore_20261031_localops`에 실제 복구했다. PC가 꺼진 동안 외부 복사는 지연되며 VM 내부 백업만 계속된다. 원격 스풀만으로 VM 밖 보관을 완료했다고 판단하지 않는다.
- `operations --watch`는 PC에서 5분마다 실제 도메인의 HTTPS/DB 상태를 검사하고 변경만 기록한다. `seelo-operations-20261031.lnk`로 로그인 시 시작한다. 알림 발송은 꺼져 있으며 상시 독립 외부 감시/알림 수신은 아직 없다.
- 카카오 GET 연결 해제 수신 코드는 배포했지만 설정은 빈 값·404다. 대표 어드민 키의 SHA-256 비교값만 보관하는 방식이며 원문 관리 키는 필요하지 않다. 등록 후 연결 해제 시 해당 카카오 연결·세션·미사용 메일 인증 토큰·가입 대기를 정리하고 계정/가게/진단 데이터는 보존한다. 현재 Chrome 제어가 Work 설정에서 비활성화돼 제공자 등록·실제 웹훅 수신은 미완료다. 별도 계정 복구·개인정보 보존 정책을 확정한 뒤 공개 운영한다.

최신 배포 태그·검증 수치·남은 항목은 [로컬 CLI 작업 기록](../../../03_실험/구현시험/로컬CLI_AI_연동진행_20261031.md)을 따른다. 운영 DB 마이그레이션·PC 재부팅·Git 커밋/푸시는 이번 작업에 없었다.
