---
tags: [运维, VPS, 部署]
created: 2026-03-17
related: [[部署方案]], [[Docker配置]], [[Nginx配置]], [[部署Runbook]], [[VPS排障清单]]
---

# VPS 部署

> 服务器部署步骤与环境配置。

> [!warning]
> 本文前半部分保留了 2026-03-17 首次上线时的历史记录。当前有效发布入口、目录结构与排障步骤请优先参考 [[部署Runbook]]。

---

## 服务器信息

| 项目 | 值 |
|------|------|
| IP | `65.75.220.11` |
| 登录 | `ssh root@65.75.220.11` |
| 域名 | `wedding.escapemobius.cc` |
| SSL | Let's Encrypt（Certbot 自动续期） |

---

## 实际部署记录（2026-03-17）

### 部署路径

VPS 上代码位于 `/opt/apps/wedding-photos/`，目录结构为扁平布局：

```
/opt/apps/wedding-photos/
├── frontend/          # 前端源码
├── backend/           # 后端源码
├── nginx-frontend.conf
├── Dockerfile.frontend
├── Dockerfile.backend
└── docker-compose.yml
```

> 注意：VPS 上是扁平结构，与本地 `src/frontend/`、`docker/Dockerfile.*` 的嵌套结构不同。Dockerfile 中的 COPY 路径已相应调整。

> [!warning]
> 上述目录结构仅代表 2026-03-17 首次上线时的阶段性状态。当前线上已回归到与本地一致的嵌套结构：
>
> - `/opt/apps/wedding-photos/src/frontend`
> - `/opt/apps/wedding-photos/src/backend`
> - `/opt/apps/wedding-photos/docker/docker-compose.yml`

### 部署步骤

```bash
# 1. 本地 rsync 到 VPS
rsync -avz src/frontend/ root@65.75.220.11:/opt/apps/wedding-photos/frontend/
rsync -avz src/backend/ root@65.75.220.11:/opt/apps/wedding-photos/backend/
rsync -avz docker/nginx-frontend.conf root@65.75.220.11:/opt/apps/wedding-photos/

# 2. VPS 上构建并启动
ssh root@65.75.220.11
cd /opt/apps/wedding-photos
docker compose build
docker compose up -d

# 3. 配置 VPS 层 Nginx（已创建 /etc/nginx/sites-enabled/wedding）
nginx -t && systemctl reload nginx
```

### Nginx 站点配置

文件：`/etc/nginx/sites-enabled/wedding`

```nginx
server {
    listen 80;
    server_name wedding.escapemobius.cc;

    location / {
        proxy_pass http://127.0.0.1:3080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> SSL 由 Cloudflare 代理处理，VPS 层仅监听 80 端口。

### 验证结果

```
https://wedding.escapemobius.cc/           → 200 ✅
https://wedding.escapemobius.cc/api/health → {"status":"ok"} ✅
```

### 踩坑记录

- VPS 目录结构扁平化后，Dockerfile 中 `COPY src/frontend/` 需改为 `COPY frontend/`
- docker-compose.yml 的 `context` 从 `..` 改为 `.`，`dockerfile` 从 `docker/Dockerfile.*` 改为 `Dockerfile.*`
- DNS 指向 Cloudflare（104.21.x），不是直连 VPS，HTTP→HTTPS 重定向由 Cloudflare 完成

---

## 更新部署

> 当前标准流程见 [[部署Runbook]]，本节仅保留历史命令示意。

```bash
cd /opt/apps/wedding-photos/docker
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d --force-recreate
docker compose -f docker-compose.yml ps
```

---

## 回滚

```bash
cd /opt/apps/wedding-photos/docker
docker compose -f docker-compose.yml down
# 之后按目标版本重新同步代码并执行标准发布
```

---

## 监控检查

```bash
# 容器状态
cd /opt/apps/wedding-photos/docker
docker compose -f docker-compose.yml ps

# 资源使用
docker stats

# 磁盘空间（注意图片存储）
df -h

# Nginx 访问日志
tail -f /var/log/nginx/access.log

# 应用日志
docker compose -f docker-compose.yml logs -f backend
```

---

## 安全检查清单

- [ ] 数据库端口未暴露公网
- [ ] API Key 通过环境变量注入，不在代码中
- [ ] 防火墙仅开放 80/443/22
- [ ] SSH 密钥登录，禁用密码登录
- [ ] 定期更新系统补丁
