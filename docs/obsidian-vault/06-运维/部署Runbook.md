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
- 当前有效 Compose project name：`wedding-photos`
- 公网入口：`https://wedding.escapemobius.cc/`

> [!warning]
> 不要依赖默认 compose project name。当前线上必须显式使用 `-p wedding-photos`，并统一以 `docker/docker-compose.yml` 为准，否则容易误打到残留的 `docker-*` 栈。

---

## 发布前检查

- 确认本地前端构建通过：`cd src/frontend && npm run build`
- 确认新增静态资源已放入 `src/frontend/public/images/`
- 确认页面资源引用统一使用 `/images/...`
- 确认没有把 `node_modules/`、`.venv/`、`__pycache__/` 一起同步到 VPS

> [!important]
> 若本次任务目标包含“VPS 验证 / 线上验证 / 真实试跑 / 本人实拍联调”，则发布完成标准不是“代码已同步”或“本地 build 通过”，而是：
> 1. 已部署到 `wedding-photos` 线上栈
> 2. 已完成指定主链路的真实线上验证
> 3. 已明确区分“本地通过”和“线上通过”

### AI 联调前准备

- 运行时密钥文件：`/opt/apps/wedding-photos/.env.runtime`
- 该文件只保存在 VPS，本地仓库和 Obsidian 不保存真实密钥
- `backend` / `acp` 通过 `docker/docker-compose.yml` 的 `env_file` 在运行时注入
- 双 key 联调时至少包含变量名：
  - `LAOZHANG_API_KEY`
  - `LAOZHANG_NANO_API_KEY`
  - `PHOTOS_PER_PACKAGE`
  - `MAX_FIX_ROUNDS`
- 联调时建议先用低成本配置：
  - `PHOTOS_PER_PACKAGE=1`
  - `MAX_FIX_ROUNDS=1`
- 不要在共享终端直接执行 `docker compose config`，该命令会展开敏感环境变量

---

## 标准发布步骤

### 1. 同步代码到 VPS

```bash
rsync -az --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.env.runtime' \
  --exclude '.env.backend' \
  ./ root@65.75.220.11:/opt/apps/wedding-photos/
```

注意：

- `--delete` 会删除目标目录中“源目录不存在”的文件
- `/.env.runtime` 属于 VPS 私有运行态密钥文件，不在仓库中，必须显式 `exclude`
- 若误删该文件，`backend` 与 `acp` 会在无 key 状态启动，表现为：
  - 上传正常
  - AI 路径异常或直接降级

### 2. 在 VPS 上重建并启动当前栈

```bash
ssh root@65.75.220.11
cd /opt/apps/wedding-photos
docker compose -p wedding-photos -f docker/docker-compose.yml build
docker compose -p wedding-photos -f docker/docker-compose.yml up -d --force-recreate
docker compose -p wedding-photos -f docker/docker-compose.yml ps
```

注意：

- 必须显式指定 `-p wedding-photos`
- 否则默认 project 名可能变成 `docker`
- 结果会额外起出一套 `docker-*` 容器，但公网 `3080` 仍可能继续走 `wedding-photos-*` 旧栈
- 表现为：
  - 你以为已经发布
  - 实际线上仍在跑旧后端

### 2.1 若误起了错误 project，立即清理

```bash
cd /opt/apps/wedding-photos/docker
docker compose -p docker -f docker-compose.yml down
```

说明：

- 这一步只用于清理误起的 `docker-*` 栈
- 不能替代正确的 `wedding-photos` 发布命令
- 若不清理，后续排障时极易把“新容器”和“真实线上容器”看混

### 3. 验证容器是否正确接管流量

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}"
curl -s http://127.0.0.1:3080/api/health
curl -I -s http://127.0.0.1:3080/
curl -I -s http://127.0.0.1:3080/images/generated-1773678492426.png
```

若本次涉及 AI 联调，再额外确认：

```bash
cat /opt/apps/wedding-photos/.env.runtime | sed 's/=.*/=[hidden]/'
curl -s http://127.0.0.1:3080/api/health/detail
```

### 4. 验证公网

```bash
curl -I -s https://wedding.escapemobius.cc/
curl -s https://wedding.escapemobius.cc/api/health
curl -I -s https://wedding.escapemobius.cc/images/generated-1773678492426.png
```

### 5. 若本次目标是真实试跑，必须补做业务链路验证

至少跑通一条真实链路，不能只停在健康检查：

```text
upload -> makeup -> create order -> start order -> wait batch -> review/download
```

若支付本轮刻意跳过，则至少验证：

```text
upload -> makeup -> create trial_free order -> start order -> deliverable download
```

验收时必须记录：

- 上传是否成功建立 session
- 试妆是否返回完整结果
- 订单是否成功进入 `processing`
- 批次是否推进到 `completed / failed`
- `deliverables` 是否真的能下载到文件

---

## 发布成功判定

满足以下 4 条才算真正发布成功：

- `wedding-photos-frontend-1` 正在运行，且映射 `0.0.0.0:3080->80/tcp`
- `wedding-photos-backend-1` 正在运行
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
- 确认本次执行的命令是否显式写了 `-p wedding-photos`
- 详见 [[VPS排障清单#场景 1：代码已部署，但公网还是旧页面]]

### 情况 1.1：误起了 `docker-*` 栈，旧 `wedding-photos-*` 仍在线

- 表现：
  - `backend` / `acp` 好像已经是新容器
  - 但 `frontend` 因 `3080` 被占用而起不来
  - 或公网仍命中旧前端
- 处理：
  1. `docker ps --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}"`
  2. 若看到同项目同时存在 `docker-*` 与 `wedding-photos-*`
  3. 先执行：
     - `docker compose -p docker -f docker/docker-compose.yml down`
  4. 再执行：
     - `docker compose -p wedding-photos -f docker/docker-compose.yml up -d --build frontend backend acp`
- 结论：
  - 这不是镜像问题，是 Compose project name 使用错误

### 情况 2：页面更新了，但插图不显示

- 先检查 `src/frontend/public/images/` 是否包含资源
- 再检查页面引用是否是 `/images/...`
- 最后检查容器内 `/usr/share/nginx/html/images/` 是否包含对应文件
- 详见 [[前端视觉资源规范#发布前校验]]

### 情况 3：`/api/health` 刚切换时返回 `502`

- 先看 `wedding-photos-backend-1` 是否刚启动
- 如果 3 到 10 秒后恢复为 `200`，通常只是后端启动未就绪
- 如果持续 `502`，查前端 Nginx upstream 与后端日志

### 情况 4：上传时返回 `413 Request Entity Too Large`

- 先检查前端 Nginx 是否已包含 `client_max_body_size 20M`
- 若缺失，重新构建 `frontend` 镜像并重启前端容器
- 后端单图限制目前仍以 `settings.max_upload_size` 为准，默认 10MB

### 情况 5：妆造接口返回 `504 Gateway Time-out`

- 先看 backend 日志里是不是仍在持续请求 Nano Banana
- 当前同步妆造接口需要依赖前端 Nginx 代理超时配置：
  - `proxy_connect_timeout 300s`
  - `proxy_send_timeout 300s`
  - `proxy_read_timeout 300s`
  - `send_timeout 300s`
- 如果后端已经生成出图片但前端超时，优先判断为网关超时，不要误判为模型失败

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
