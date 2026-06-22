FROM oven/bun:latest AS build

WORKDIR /app
COPY agent-workbench/web/package.json ./
# 本地已有 Bun 镜像时可离线构建 Vite 前端，避免额外拉 node:20-alpine。
RUN bun install

COPY agent-workbench/web ./
ARG VITE_API_BASE_URL=http://localhost:18088
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN bun run build

FROM nginx:latest
# 这里只托管静态工作台页面，API 地址由构建参数 VITE_API_BASE_URL 固化。
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
