---
tags: [运维, Docker, 容器化]
created: 2026-03-17
related: [[部署方案]], [[VPS部署]], [[Nginx配置]], [[系统架构]]
---

# Docker 配置

> Docker 容器化配置记录，配置文件位于 `docker/` 目录。

---

## 文件清单

| 文件 | 路径 | 用途 |
|------|------|------|
| docker-compose.yml | `docker/docker-compose.yml` | 编排服务 |
| Dockerfile.frontend | `docker/Dockerfile.frontend` | 前端镜像 |
| Dockerfile.backend | `docker/Dockerfile.backend` | 后端镜像 |
| nginx-frontend.conf | `docker/nginx-frontend.conf` | 前端容器内 Nginx 配置 |

---

## docker-compose.yml

```yaml
services:
  frontend:
    build:
      context: ..
      dockerfile: docker/Dockerfile.frontend
    ports:
      - "3080:80"
    depends_on:
      - backend

  backend:
    build:
      context: ..
      dockerfile: docker/Dockerfile.backend
    expose:
      - "8000"    # 仅内部暴露，不映射到主机
    environment:
      - NANO_API_KEY=${NANO_API_KEY}
      - GPT_API_KEY=${GPT_API_KEY}
```

关键点：
- 后端使用 `expose` 而非 `ports`，仅容器网络内可访问
- 数据库端口不暴露（安全红线）
- API Key 通过环境变量注入

---

## Dockerfile.frontend

```dockerfile
# 构建阶段
FROM node:20-alpine AS builder
WORKDIR /app
COPY src/frontend/package*.json ./
RUN npm install
COPY src/frontend/ ./
RUN npm run build

# 运行阶段
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY docker/nginx-frontend.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

多阶段构建：
1. Node 环境构建前端产物
2. Nginx 镜像仅包含静态文件

---

## Dockerfile.backend

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY src/backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY src/backend/ ./
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 前端容器 Nginx 配置

参见 [[Nginx配置]] 获取完整配置说明。

核心功能：
- 服务静态文件
- SPA 路由 fallback 到 `index.html`

---

## 常用命令

```bash
# 构建所有镜像
docker-compose -f docker/docker-compose.yml build

# 启动所有服务
docker-compose -f docker/docker-compose.yml up -d

# 查看日志
docker-compose -f docker/docker-compose.yml logs -f

# 重建并启动
docker-compose -f docker/docker-compose.yml up -d --build

# 停止所有服务
docker-compose -f docker/docker-compose.yml down

# 清理无用镜像
docker image prune -f
```

---

## 端口规划

详见 [[系统架构#Docker 端口规划]]。

| 服务 | 容器端口 | 主机端口 |
|------|----------|----------|
| 前端 Nginx | 80 | 3080 |
| 后端 Uvicorn | 8000 | 仅内部 |

---

## 网络

Docker Compose 默认创建 bridge 网络，前端容器可通过服务名 `backend` 访问后端：

```
http://backend:8000/api/...
```

VPS 层 Nginx 通过 `localhost:3080` 访问前端容器，通过 `localhost:8000` 访问后端容器（如果映射了端口的话）。实际方案中后端通过前端容器内 Nginx 反代。
