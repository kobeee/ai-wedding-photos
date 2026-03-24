---
tags: [AI管线, API, Gemini, 图像生成]
created: 2026-03-17
related: [[GPT-Image-1.5]], [[双模型协作]], [[VLM质检管线]], [[API设计]], [[上下文工程]], [[上下文工程-工程落地版]]
---

# Nano-Banana-Pro

> Gemini Nano Banana Pro 图像生成模型，项目中负责 4K 底图渲染和物理错误修复。
> 在 [[双模型协作]] 中承担**画质与 ID 保持**的主攻角色。

---

## 模型定位

| 维度 | 说明 |
|------|------|
| 全称 | Gemini 3 Pro Image Preview（Nano Banana Pro） |
| 擅长 | 高画质渲染、ID 保持、物理准确性 |
| 在项目中的角色 | 4K 底图生成 + 物理错误局部重绘 |
| 搭档 | [[GPT-Image-1.5]]（情绪重绘） |

---

## API 配置

### Endpoint

```
https://api.laozhang.ai/v1beta/models/gemini-3-pro-image-preview:generateContent
```

### 鉴权

```
Authorization: Bearer $API_KEY
```

---

## 文生图

从文本 Prompt 生成图像。

### 请求示例

```json
{
  "contents": [
    {
      "parts": [
        {
          "text": "一对中国新人在极光下的婚纱照，新娘白色拖尾婚纱，新郎深色西装，电影级光影，8K画质"
        }
      ]
    }
  ],
  "generationConfig": {
    "responseModalities": ["IMAGE"],
    "imageConfig": {
      "aspectRatio": "3:4",
      "imageSize": "1024"
    }
  }
}
```

### 响应解析

```javascript
// 图片数据在 base64 编码中
const imageData = response.candidates[0].content.parts[0].inlineData.data;
const mimeType = response.candidates[0].content.parts[0].inlineData.mimeType;

// 解码为图片
const imageBuffer = Buffer.from(imageData, 'base64');
```

### generationConfig 参数

| 参数 | 说明 | 可选值 |
|------|------|--------|
| `responseModalities` | 响应类型 | `["IMAGE"]`, `["TEXT", "IMAGE"]` |
| `imageConfig.aspectRatio` | 宽高比 | `"1:1"`, `"3:4"`, `"4:3"`, `"16:9"`, `"9:16"` |
| `imageConfig.imageSize` | 图像尺寸 | `"256"`, `"512"`, `"1024"` |

---

## 图生图

传入参考图 + 文本 Prompt，生成新图像。用于 [[VLM质检管线]] 中的物理错误修复。

### 请求示例

```json
{
  "contents": [
    {
      "parts": [
        {
          "text": "基于参考照片中的人物，生成一张极光背景的婚纱照，保持人物面部特征不变"
        },
        {
          "inline_data": {
            "mime_type": "image/jpeg",
            "data": "<base64_encoded_image_data>"
          }
        }
      ]
    }
  ],
  "generationConfig": {
    "responseModalities": ["IMAGE"],
    "imageConfig": {
      "aspectRatio": "3:4",
      "imageSize": "1024"
    }
  }
}
```

### 多图参考

支持混合多图参考，在 `parts` 数组中传入多个 `inline_data`：

```json
{
  "contents": [
    {
      "parts": [
        { "text": "Prompt 描述..." },
        { "inline_data": { "mime_type": "image/jpeg", "data": "<img1_base64>" } },
        { "inline_data": { "mime_type": "image/jpeg", "data": "<img2_base64>" } },
        { "inline_data": { "mime_type": "image/jpeg", "data": "<img3_base64>" } }
      ]
    }
  ]
}
```

**限制**：
- 最多 **14 张**参考图
- 建议分配：**6 张**高保真对象图 + **5 张**人物图
- 图片过多会影响生成速度和质量

---

## 带 Google 搜索工具

启用 Google 搜索增强，适用于需要参考真实场景的生成。

### 请求示例

```json
{
  "contents": [
    {
      "parts": [
        {
          "text": "生成一张在冰岛蓝湖温泉拍摄的婚纱照"
        }
      ]
    }
  ],
  "tools": [
    { "google_search": {} }
  ],
  "generationConfig": {
    "responseModalities": ["TEXT", "IMAGE"]
  }
}
```

**注意**：启用搜索时，`responseModalities` 需包含 `"TEXT"` 和 `"IMAGE"`，因为搜索结果会以文本形式返回。

---

## 在项目中的调用场景

| 场景 | 模式 | 触发位置 |
|------|------|----------|
| AI 试妆预览 | 图生图 | [[用户旅程#Step 2：AI试妆]] |
| 4K 底图渲染 | 文生图/图生图 | [[用户旅程#Step 4：沉浸式等待]] |
| 物理错误修复 | 图生图（局部） | [[VLM质检管线]] |

---

## 注意事项

- API Key 通过环境变量注入，不硬编码
- 生成失败需要重试机制（最多 3 次）
- 大图生成耗时较长，需要异步处理
- 并发请求注意 Rate Limit
