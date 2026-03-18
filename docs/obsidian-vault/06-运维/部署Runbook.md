---
tags: [运维, 部署, Runbook]
created: 2026-03-19
related: [[VPS部署]], [[Docker配置]], [[Nginx配置]], [[VPS排障清单]], [[踩坑记录]]
---

# 部署 Runbook

> 当前项目的标准发布流程。目标是一次部署、一次验证、一次定性，避免“代码已同步但公网仍是旧站”。

---

## 适用范围

- 部署目标：`root@65.75.220.11`
- 代码路径：`/opt/apps/wedding-photos/`
- 当前有效 Compose 文件：`/opt/apps/wedding-photos/docker/docker-compose.yml`
- 公网入口：`https://wedding.escapemobius.cc/`

> [!warning]
> 不要再使用仓库根目录的 `docker-compose.yml` 思维模型。当前线上以 `docker/docker-compose.yml` 为准。

---

## 发布前检查

- 确认本地前端构建通过：`cd src/frontend && npm run build`
- 确认新增静态资源已放入 `src/frontend/public/images/`
- 确认页面资源引用统一使用 `/images/...`
- 确认没有把 `node_modules/`、`.venv/`、`__pycache__/` 一起同步到 VPS

---

## 标准发布步骤

### 1. 同步代码到 VPS

```bash
rsync -az --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  ./ root@65.75.220.11:/opt/apps/wedding-photos/
```

### 2. 在 VPS 上重建并启动当前栈

```bash
ssh root@65.75.220.11
cd /opt/apps/wedding-photos/docker
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d --force-recreate
docker compose -f docker-compose.yml ps
```

### 3. 验证容器是否正确接管流量

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}"
curl -s http://127.0.0.1:3080/api/health
curl -I -s http://127.0.0.1:3080/
curl -I -s http://127.0.0.1:3080/images/generated-1773678492426.png
```

### 4. 验证公网

```bash
curl -I -s https://wedding.escapemobius.cc/
curl -s https://wedding.escapemobius.cc/api/health
curl -I -s https://wedding.escapemobius.cc/images/generated-1773678492426.png
```

---

## 发布成功判定

满足以下 4 条才算真正发布成功：

- `docker-frontend-1` 正在运行，且映射 `0.0.0.0:3080->80/tcp`
- `docker-backend-1` 正在运行
- `https://wedding.escapemobius.cc/` 返回 `200`
- 公网插图 URL 返回 `200`，而不是只验证首页 HTML

---

## 强制检查项

每次发布后都必须检查：

1. `docker ps` 中是否还存在历史婚纱站容器
2. `3080` 当前绑定的是不是新前端容器
3. 后端健康接口是启动中短暂失败，还是长期 `502`
4. 插图资源能否通过公网直接访问

---

## 常见异常与处理

### 情况 1：新镜像构建成功，但公网还是旧页面

- 优先怀疑旧容器还在占用 `3080`
- 先执行 `docker ps`，确认是否同时存在 `wedding-photos-*` 和 `docker-*`
- 详见 [[VPS排障清单#场景 1：代码已部署，但公网还是旧页面]]

### 情况 2：页面更新了，但插图不显示

- 先检查 `src/frontend/public/images/` 是否包含资源
- 再检查页面引用是否是 `/images/...`
- 最后检查容器内 `/usr/share/nginx/html/images/` 是否包含对应文件
- 详见 [[前端视觉资源规范#发布前校验]]

### 情况 3：`/api/health` 刚切换时返回 `502`

- 先看 `docker-backend-1` 是否刚启动
- 如果 3 到 10 秒后恢复为 `200`，通常只是后端启动未就绪
- 如果持续 `502`，查前端 Nginx upstream 与后端日志

---

## 推荐的发布后人工复验

1. 无痕窗口打开首页
2. 打开 `/upload`
3. 打开 `/makeup`
4. 强刷一遍，确认不是本地缓存
5. 如果视觉稿对齐是本次目标，再做截图对比

---

## 相关文档

- [[VPS部署]] — 服务器信息与基础部署说明
- [[VPS排障清单]] — 线上发布异常的速查清单
- [[前端视觉资源规范]] — 视觉资源放置与引用规则
- [[踩坑记录]] — 历史问题与教训沉淀
