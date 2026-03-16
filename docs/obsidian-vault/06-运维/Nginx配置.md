---
tags: [运维, Nginx, 反向代理]
created: 2026-03-17
related: [[部署方案]], [[Docker配置]], [[VPS部署]], [[系统架构]]
---

# Nginx 配置

> 项目使用两层 Nginx：容器内（前端静态资源）+ VPS 层（反向代理 + SSL）。

---

## 架构说明

```
用户 → HTTPS → VPS Nginx(443) → Docker Frontend Nginx(3080:80)
                     └──── /api/* → Docker Backend(8000)
```

参见 [[部署方案#Nginx 两层代理]]。

---

## 容器内 Nginx（前端）

文件位置：`docker/nginx-frontend.conf`

### 功能
- 服务前端静态资源（Vite 构建产物）
- SPA 路由 fallback 到 `index.html`

### 配置

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # SPA 路由 fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 静态资源缓存
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # 禁止访问隐藏文件
    location ~ /\. {
        deny all;
    }
}
```

关键：`try_files $uri $uri/ /index.html;` 确保所有路由（`/upload`, `/makeup` 等）都能正确加载 SPA。没有这行会导致刷新页面 404 —— 参见 [[踩坑记录]]。

---

## VPS 层 Nginx

文件位置：`/etc/nginx/sites-available/wedding.escapemobius.cc`

### 功能
- SSL 终止（HTTPS）
- 域名路由
- 反向代理到 Docker 容器
- `/api/` 路径反代到后端

### 配置

```nginx
server {
    listen 443 ssl http2;
    server_name wedding.escapemobius.cc;

    # SSL 证书（Let's Encrypt）
    ssl_certificate /etc/letsencrypt/live/wedding.escapemobius.cc/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/wedding.escapemobius.cc/privkey.pem;

    # 前端静态资源
    location / {
        proxy_pass http://127.0.0.1:3080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 后端 API 反代
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 上传文件大小限制
        client_max_body_size 50M;

        # 长连接（生成任务可能耗时较长）
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
    }
}

# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name wedding.escapemobius.cc;
    return 301 https://$host$request_uri;
}
```

### 关键配置说明

| 配置项 | 值 | 原因 |
|--------|------|------|
| `client_max_body_size` | 50M | 用户上传多张照片 |
| `proxy_read_timeout` | 120s | AI 生成耗时可达 60s |
| `proxy_connect_timeout` | 10s | 快速发现后端不可用 |

---

## 常用命令

```bash
# 测试配置语法
nginx -t

# 重载配置（不中断服务）
systemctl reload nginx

# 重启 Nginx
systemctl restart nginx

# 查看错误日志
tail -f /var/log/nginx/error.log

# 查看访问日志
tail -f /var/log/nginx/access.log
```

---

## SSL 证书管理

```bash
# 首次申请
certbot --nginx -d wedding.escapemobius.cc

# 手动续期
certbot renew

# 自动续期（crontab 通常已自动配置）
# 0 0 1 * * certbot renew --quiet
```

---

## 注意事项

- VPS 上已有多个服务，wedding 配置是独立站点文件
- 修改配置前先 `nginx -t` 测试
- `/api/` 反代路径末尾的斜杠很重要，不要遗漏
- 上传超时问题检查 `client_max_body_size` 和 `proxy_read_timeout`
