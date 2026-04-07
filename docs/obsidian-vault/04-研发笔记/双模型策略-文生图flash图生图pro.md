# 双模型策略：文生图 Flash + 图生图 Pro

## 日期
2026-04-07

## 背景
端到端测试暴露 V14 代码未部署到 VPS（跑的是旧四轮法），同时 API 调用成本高。
结合 GPT-Image-2、Git-6 等下一代模型消息，确立"产品先行、模型可换"的战略方向。

## 决策
将 Nano Banana 服务拆分为双模型调用策略：

| 场景 | 模型 | 理由 |
|------|------|------|
| **文生图** (text_to_image) | gemini-3.1-flash-image-preview | 无参考图输入，flash 速度快、成本低 |
| **图生图** (image_to_image, multi_reference_generate, repair_with_references) | gemini-3-pro-image-preview | 需要理解参考图细节，pro 质量更高 |

## 代码改动

### config.py
- 新增 `nano_banana_txt2img_model: str = "gemini-3.1-flash-image-preview"`
- 原 `nano_banana_model` 保留给图生图

### services/nano_banana.py
- `__init__` 新增 `self.txt2img_api_url` 指向 flash 模型
- `_generate_from_parts` 新增 `api_url` 可选参数，支持调用方指定 URL
- `text_to_image` 传入 `api_url=self.txt2img_api_url` 走 flash
- `image_to_image` / `multi_reference_generate` / `repair_with_references` 不变，默认走 pro

### routers/health.py
- health/detail 新增 `nano_banana_txt2img_model` 字段

## 架构原则
- 调用方式和 API Key 完全一致，只是模型名不同
- 通过 config 字段控制，环境变量可覆盖
- 未来模型升级只需改 config 默认值

## 关联
- [[V14-管线全面重构方案]] — V14 管线代码已改但未部署
- [[../07-日志/2026-04-07]] — 端到端测试失败复盘
