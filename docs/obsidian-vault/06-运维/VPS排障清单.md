---
tags: [运维, VPS, 排障]
created: 2026-03-19
related: [[部署Runbook]], [[VPS部署]], [[Nginx配置]], [[踩坑记录]]
---

# VPS 排障清单

> 面向“已经部署了，但线上表现不对”的场景。先定性，再修复，不要盲目重复部署。

---

## 场景 1：代码已部署，但公网还是旧页面

### 快速判断

```bash
ssh root@65.75.220.11
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}"
```

### 重点看什么

- 是否同时存在两套婚纱站容器
- `3080` 当前绑在哪个前端容器上
- Compose project name 是否混用了 `wedding-photos-*` 和 `docker-*`

### 典型根因

- 改了 compose 所在目录，导致 project name 变化
- 旧栈残留容器未清理
- 新前端容器成功构建，但没有接管 `3080`

### 处理方式

```bash
cd /opt/apps/wedding-photos
docker compose -p wedding-photos -f docker/docker-compose.yml ps
docker compose -p wedding-photos -f docker/docker-compose.yml up -d frontend
```

如果 `3080` 明确仍被错误栈占用，再定向清理残留容器，而不是盲目 `docker rm -f` 当前有效栈。

---

## 场景 2：首页能打开，但插图全部丢失

### 快速判断

```bash
curl -I -s https://wedding.escapemobius.cc/images/generated-1773678492426.png
```

### 分层排查顺序

1. 本地仓库是否有文件：`src/frontend/public/images/`
2. 页面代码是否引用 `/images/...`
3. 容器内是否存在文件：`/usr/share/nginx/html/images/`
4. 公网 URL 是否返回 `200`

### 常见根因

- 资源放错目录，没有进入 Vite `public/`
- 代码引用路径不统一
- 构建产物没更新到容器
- 误以为是资源缺失，实际是公网仍命中旧栈

---

## 场景 3：切换后 `/api/health` 返回 `502`

### 判断标准

- 如果刚重启 1 到 5 秒内出现，优先视为后端启动未就绪
- 如果持续返回 `502`，再查配置或网络

### 排查命令

```bash
docker logs --tail 60 wedding-photos-frontend-1
docker logs --tail 60 wedding-photos-backend-1
curl -i -s http://127.0.0.1:3080/api/health
```

### 重点看什么

- 前端 Nginx 是否报 `connect() failed (111: Connection refused)`
- 后端是否已经完成 startup
- Nginx upstream 指向的容器地址和端口是否正确

---

## 场景 4：本机看着对，用户仍反馈线上不对

### 先排除缓存

- 让用户使用无痕窗口
- 强刷页面
- 再访问一张插图 URL 验证是否命中新资源

### 再看公网返回头

```bash
curl -I -s https://wedding.escapemobius.cc/
curl -I -s https://wedding.escapemobius.cc/images/generated-1773678492426.png
```

### 说明

- 如果首页和插图都返回新时间戳，通常不是 CDN 旧缓存
- 如果用户仍看到旧样式，优先怀疑本地缓存或截图时机

---

## 速查命令

```bash
# 容器总览
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}"

# 当前栈状态
cd /opt/apps/wedding-photos
docker compose -p wedding-photos -f docker/docker-compose.yml ps

# 后端健康
curl -s http://127.0.0.1:3080/api/health

# 公网首页
curl -I -s https://wedding.escapemobius.cc/

# 公网插图
curl -I -s https://wedding.escapemobius.cc/images/generated-1773678492426.png
```

---

## 结论原则

- 只验证首页 `200` 不够
- 必须同时验证：容器、健康接口、首页 HTML、插图 URL
- 一旦涉及 compose 路径变化，第一反应就是查残留旧容器
