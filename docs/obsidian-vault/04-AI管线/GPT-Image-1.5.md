---
tags: [AI管线, API, OpenAI, 图像编辑]
created: 2026-03-17
related: [[Nano-Banana-Pro]], [[双模型协作]], [[VLM质检管线]], [[API设计]], [[上下文工程]], [[上下文工程-工程落地版]]
---

# GPT-Image-1.5

> OpenAI gpt-image-1.5 图像生成/编辑模型。
> 当前项目中 **保留服务封装与配置开关，但默认不进入生产修复链路**；待后续补齐遮罩与效果评估后，再决定是否恢复到 [[双模型协作]]。

---

## 模型定位

| 维度 | 说明 |
|------|------|
| 模型名 | gpt-image-1.5 |
| 擅长 | 面部表情控制、情绪重绘、精细局部编辑 |
| 在项目中的角色 | 预留的情绪错误修复、面部精修实验位 |
| 搭档 | [[Nano-Banana-Pro]]（底图渲染） |

---

## API 配置

### Base URL

```
https://api.laozhang.ai/v1
```

### 鉴权

```
Authorization: Bearer $API_KEY
```

---

## 文生图

从文本 Prompt 生成图像。

### 请求示例

```python
import openai

client = openai.OpenAI(
    api_key="$API_KEY",
    base_url="https://api.laozhang.ai/v1"
)

response = client.images.generate(
    model="gpt-image-1.5",
    prompt="一位微笑的中国新娘，精致妆容，白色婚纱，暖色光影，电影级画质",
    n=1,
    size="1536x1024",
    quality="high",
    output_format="png"
)

# 获取图片数据
image_data = response.data[0].b64_json  # 或 response.data[0].url
```

### 参数说明

| 参数 | 类型 | 说明 | 可选值 |
|------|------|------|--------|
| `model` | string | 模型名 | `"gpt-image-1.5"` |
| `prompt` | string | 文本提示 | - |
| `n` | int | 生成数量 | 1-4 |
| `size` | string | 图片尺寸 | `"auto"`, `"1024x1024"`, `"1536x1024"`, `"1024x1536"` |
| `quality` | string | 质量 | `"auto"`, `"high"` |
| `output_format` | string | 输出格式 | `"png"`, `"jpeg"` |
| `output_compression` | int | 压缩比（可选） | 0-100，仅 jpeg 有效 |

### 尺寸选择建议

| 场景 | 推荐尺寸 |
|------|----------|
| 竖版婚纱照 | `1024x1536` |
| 横版婚纱照 | `1536x1024` |
| 方形头像 | `1024x1024` |
| 自动选择 | `"auto"` |

---

## 图生图（编辑）

基于现有图片进行编辑。当前仓库保留这套能力，但默认关闭。

### 基本编辑

```python
response = client.images.edit(
    model="gpt-image-1.5",
    image=open("source.png", "rb"),
    prompt="将新娘的表情调整为幸福的微笑，保持其他部分不变",
    n=1,
    size="1536x1024"
)
```

### 带遮罩的局部重绘

```python
response = client.images.edit(
    model="gpt-image-1.5",
    image=open("source.png", "rb"),
    mask=open("mask.png", "rb"),      # 遮罩区域会被重绘
    prompt="在遮罩区域绘制温暖的微笑表情",
    n=1,
    size="1536x1024"
)
```

### 遮罩说明

- 遮罩图与源图**尺寸必须一致**
- **白色区域**（255）= 需要重绘的区域
- **黑色区域**（0）= 保持不变的区域
- 格式：PNG，带 Alpha 通道

### 使用场景

| 场景 | 方式 |
|------|------|
| 表情修复 | 遮罩面部区域 + 情绪 Prompt |
| 对象移除 | 遮罩目标区域 + "移除" Prompt |
| 局部重绘 | 遮罩指定区域 + 描述性 Prompt |
| 风格调整 | 全图编辑（无遮罩） |

---

## 在项目中的调用场景

| 场景 | 模式 | 触发位置 |
|------|------|----------|
| 情绪错误修复 | 图生图（遮罩） | 仅在后续实验开关开启时 |
| 面部精修 | 图生图（遮罩） | 仅在后续实验开关开启时 |
| 表情微调 | 图生图 | 魔法笔刷功能 |

---

## 与 Nano-Banana-Pro 的分工

参见 [[双模型协作]] 的完整协作策略。

| 维度 | [[Nano-Banana-Pro]] | GPT-Image-1.5 |
|------|---------------------|---------------|
| 主攻 | 画质 + ID 保持 | 表情 + 情绪 |
| 模式 | 文生图 / 多图参考 | 图编辑 / 遮罩重绘 |
| 调用时机 | 底图生成 + 当前全部修复 | 预留实验开关 |

---

## 注意事项

- API Key 通过环境变量注入
- 编辑模式下源图会被压缩，注意质量损失
- `quality: "high"` 会增加生成时间但显著提升质量
- Rate Limit 较严格，需要排队机制
- 若要恢复生产使用，必须先证明“遮罩 edit + face 区域定位”确实优于 Nano-only repair
