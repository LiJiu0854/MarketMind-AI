FROM registry-1.docker.io/library/node:22.23.2-alpine3.24 AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM registry-1.docker.io/library/nginx:1.30.5-alpine3.24
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
