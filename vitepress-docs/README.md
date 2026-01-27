# EZmodel API 文档

基于 VitePress 构建的 EZmodel API 文档站点。

## 开发

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run docs:dev

# 构建生产版本
npm run docs:build

# 预览构建结果
npm run docs:preview
```

## Docker 部署

```bash
# 使用 docker-compose
docker-compose up -d --build

# 或直接使用 Docker
docker build -t ezmodel-docs .
docker run -d -p 3100:80 ezmodel-docs
```

访问地址：`http://localhost:3100`

## 目录结构

```
.
├── .vitepress/          # VitePress 配置
│   └── config.mts       # 站点配置
├── api/                 # API 文档
│   ├── audio/           # 音频 API
│   ├── chat/            # 聊天 API
│   ├── image/           # 图像 API
│   └── video/           # 视频 API
├── en/                  # 英文文档
├── guide/               # 入门指南
├── kling/               # Kling 视频文档
├── sora/                # Sora 视频文档
├── public/              # 静态资源
├── index.md             # 首页
├── Dockerfile           # Docker 构建文件
└── docker-compose.yml   # Docker Compose 配置
```

## 企业合作

联系邮箱：service@ezmodel.cloud
