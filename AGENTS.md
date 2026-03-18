# AI高定婚纱摄影 - 项目规则

## 项目概述
基于双核大模型（Gemini Nano Banana Pro + OpenAI gpt-image-1.5）与Agentic Workflow的AI婚纱摄影Web平台。

## 技术架构
- 前后端分离，源码统一在 `src/` 目录下
  - `src/frontend/` - React 19 + TypeScript + Vite 8 + React Router v7 + Lucide React
  - `src/backend/` - Python FastAPI + httpx + pydantic-settings + Pillow
- Docker + docker-compose 部署
- 部署目标：VPS root@65.75.220.11
- 域名：wedding.escapemobius.cc（Cloudflare 代理 → VPS nginx → Docker 容器）

## 当前项目状态
- 前端：6 页面 + 2 公共组件，UI 完成
- 后端：4 路由（health/upload/makeup/generate）+ 3 AI 服务 + 存储工具
- 部署：已上线 https://wedding.escapemobius.cc ✅
- AI 管线：代码就绪，待注入 LAOZHANG_API_KEY 联调
- 知识库：8 目录 21+ 文档，知识图谱互链

## 关键路径
- 前端页面：`src/frontend/src/pages/` (Landing/Upload/Makeup/PackageSelect/Waiting/Review)
- 后端路由：`src/backend/routers/` (health/upload/makeup/generate)
- AI 服务：`src/backend/services/` (nano_banana/gpt_image/vlm_checker)
- 配置：`src/backend/config.py`（pydantic-settings，读 .env）
- 设计稿：`page.pen`（6 页面完整设计）

## 部署子 agent（/agents 可见）

- **位置**：`.claude/agents/deploy.md`，在 Claude Code 中运行 `/agents` 可见
- **职责**：仅执行 VPS 部署，不解决项目/代码问题
- **执行方式**：委托给 iflow（glm-5 + YOLO），部署工作在 iflow 进程中完成，**不消耗主 agent token**
- **调用**：`/deploy 执行标准部署` 或对主 agent 说「用 deploy agent 部署」
- **通信**：若 iflow 输出 `[部署受阻]`，主 agent 需接手处理代码问题

## VPS 部署信息
- 代码路径：`/opt/apps/wedding-photos/`（扁平结构，非嵌套）
- 容器：frontend(3080:80) + backend(expose 8000)
- VPS nginx：`/etc/nginx/sites-enabled/wedding` → proxy_pass 127.0.0.1:3080
- SSL：Cloudflare 处理，VPS 层仅 HTTP
- 更新部署：rsync → docker compose build → docker compose up -d

## API 代理
- 统一通过 laozhang.ai 代理调用
- Nano Banana Pro：`https://api.laozhang.ai/v1beta/models/gemini-3-pro-image-preview:generateContent`
- GPT-Image-1.5：`https://api.laozhang.ai/v1`，model `gpt-image-1`
- 环境变量：`LAOZHANG_API_KEY`

## 安全红线
- 数据库端口严禁暴露公网
- 用户面部数据生成后24小时内自动销毁（periodic_cleanup）
- 所有API接口必须鉴权

## 研发流程规范
- 关键决策、技术方案、问题排查等研发记录必须沉淀到 Obsidian 知识库
- 知识库路径：`docs/obsidian-vault/`（8 个分类目录）
- 不擅自提交 git，由用户决定提交时机
- 设计稿先行，代码实现跟随视觉稿
- 大文件分段写入，不再询问

## 设计规范
- 视觉稿在 page.pen 中完成
- 深色奢华主题：#0A0A0A 底 + #C9A96E 金色点缀
- 面向95后/00后用户，高端、简约、沉浸式
- 去AI化体验，全流程隐藏技术参数
- CSS Variables 设计系统（17 个 Token）
- 完整设计上下文见 `.impeccable.md`

## Design Context (Impeccable)

### 品牌性格
浪漫 · 极简 · 沉浸

### 参考方向
- Apple 官网：极简留白、大图沉浸、动效克制但精致
- Squarespace 模板：摄影师作品集感，图片主导，文字辅助
- 反面：传统影楼官网（花哨、信息过载、弹窗满天飞）

### 设计五原则
1. **少即是多** — 每个页面只做一件事，留白本身就是设计
2. **图片即叙事** — 大面积高质量图片传递价值，文字只做辅助
3. **仪式感大于效率** — 每一步都是精心策划的体验，等待是"期待"不是"忍耐"
4. **克制的奢华** — 金色点缀传递品质感但绝不过度，优雅来自克制
5. **零决策压力** — 视觉引导替代文字说明，默认推荐替代复杂选择
