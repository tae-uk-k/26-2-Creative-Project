# 프런트 빌드 결과를 nginx 정적 파일로 제공한다. /api 프록시·보안 헤더는 마운트한 nginx 설정이 담당한다.
# 기반 이미지 버전은 package.json engines(Node 22.12 이상)와 운영 nginx 버전에 맞춘다.
ARG NODE_IMAGE=node:22.16.0-bookworm-slim
ARG NGINX_IMAGE=nginx:1.30.6

FROM ${NODE_IMAGE} AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# 스마트스토어 위임 안내에 보여 줄 seelo 담당자. 판매자에게 공개하는 값이며 비밀값이 아니다.
ARG VITE_SEELO_MANAGER_NAME=
ARG VITE_SEELO_MANAGER_PHONE=
# tsc --noEmit 후 vite build. 타입 오류가 있으면 이미지를 만들지 않는다.
RUN npm run build

FROM ${NGINX_IMAGE}
COPY --from=build /app/dist /usr/share/nginx/html
