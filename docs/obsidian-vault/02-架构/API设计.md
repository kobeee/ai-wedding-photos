---
tags: [架构, API, 后端]
created: 2026-03-17
related: [[系统架构]], [[后端开发]], [[用户旅程]], [[Nano-Banana-Pro]], [[GPT-Image-1.5]]
---

# API 设计

> RESTful 接口定义，所有接口通过 Nginx 反代 `/api/` 路径访问。
> 部署架构参见 [[系统架构#部署架构]]，Nginx 配置见 [[Nginx配置]]。

---

## Base URL

```
生产环境: https://wedding.escapemobius.cc/api
开发环境: http://localhost:8000/api
```

---

## 接口清单

### POST /api/upload

上传用户照片，建立数字档案。

```
POST /api/upload
Content-Type: multipart/form-data

参数:
  - files: File[]       # 用户照片，5-10张
  - gender: string      # "male" | "female"
  - session_id: string  # 可选，续传时使用

响应 200:
{
  "archive_id": "uuid",
  "uploaded_count": 5,
  "face_embeddings_status": "processing" | "ready",
  "message": "上传成功"
}
```

对应前端页面：Upload，参见 [[用户旅程#Step 1：建立档案]]。

---

### POST /api/makeup/generate

生成 AI 试妆效果图。

```
POST /api/makeup/generate
Content-Type: application/json

参数:
{
  "archive_id": "uuid",
  "style": "natural" | "refined" | "bone_sculpt"
}

响应 200:
{
  "previews": [
    {"url": "https://...", "style": "natural"},
    {"url": "https://...", "style": "refined"},
    {"url": "https://...", "style": "bone_sculpt"}
  ],
  "selected_embedding_id": "uuid"
}
```

后端调用 [[Nano-Banana-Pro#图生图]] 生成预览。

---

### POST /api/generate

提交生成婚纱照任务。

```
POST /api/generate
Content-Type: application/json

参数:
{
  "archive_id": "uuid",
  "package_id": "string",        # 套餐 ID
  "makeup_embedding_id": "uuid", # 试妆选择结果
  "count": 20                    # 生成张数
}

响应 202:
{
  "task_id": "uuid",
  "estimated_seconds": 45,
  "message": "任务已提交"
}
```

触发完整 AI 管线：[[Nano-Banana-Pro]] 底图渲染 → [[VLM质检管线]] → [[双模型协作]] 修复。

---

### GET /api/generate/{task_id}/status

查询生成任务状态。

```
GET /api/generate/{task_id}/status

响应 200:
{
  "task_id": "uuid",
  "status": "pending" | "generating" | "quality_check" | "fixing" | "completed" | "failed",
  "progress": 0.65,
  "current_step": "AI正在为您精心布光...",
  "fix_round": 1,        # 当前修复轮次（0-3）
  "estimated_remaining": 15
}
```

前端等待页轮询此接口，参见 [[用户旅程#Step 4：沉浸式等待]]。

---

### GET /api/generate/{task_id}/result

获取生成结果。

```
GET /api/generate/{task_id}/result

响应 200:
{
  "task_id": "uuid",
  "images": [
    {
      "id": "uuid",
      "url_preview": "https://...720p.jpg",
      "url_4k": "https://...4k.jpg",
      "url_8k": "https://...8k.jpg",    # 付费后可用
      "has_watermark": true               # 免费版带水印
    }
  ],
  "quality_score": 0.92,
  "fix_rounds_used": 1
}
```

审片页获取此数据，参见 [[用户旅程#Step 5：审片与交付]]。

---

## 错误码规范

| 状态码 | 含义 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 403 | 付费功能未解锁 |
| 404 | 资源不存在 |
| 429 | 请求过于频繁 |
| 500 | 服务器内部错误 |
| 503 | AI 服务暂时不可用 |

---

## 鉴权方案

Phase 1 使用简单的 session token，后续迭代引入 JWT。

```
Authorization: Bearer <session_token>
```
