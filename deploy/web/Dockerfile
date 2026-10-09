# Static UI + same-origin /api reverse proxy. Build context: repo root.
FROM node:22-alpine AS build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# tsc type-checks tests too; they import these shared fixtures from docs/.
COPY docs/*.json /src/docs/
# Same origin: the browser calls /api, nginx forwards to the isolated API container.
ENV VITE_API_URL=/api VITE_CHAIN_ID=84532
RUN npm run build

FROM nginxinc/nginx-unprivileged:alpine
COPY deploy/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/frontend/dist /usr/share/nginx/html
EXPOSE 8080
