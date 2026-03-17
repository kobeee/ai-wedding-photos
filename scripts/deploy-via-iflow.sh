#!/usr/bin/env bash
#
# 部署子 agent 调用脚本
# 使用 iflow CLI 执行 VPS 部署，默认 glm-5 模型 + YOLO 模式
# 主 agent（Claude Code）通过此脚本委托部署任务，以节省自身 token 消耗
#
# 用法:
#   ./scripts/deploy-via-iflow.sh                    # 交互式，输入部署任务
#   ./scripts/deploy-via-iflow.sh "执行标准部署"      # 非交互式，直接执行
#

set -e
cd "$(dirname "$0")/.."

# iflow 部署专用配置
export IFLOW_contextFileName="IFLOW_DEPLOY.md"
export IFLOW_modelName="glm-5"
export IFLOW_approvalMode="yolo"

# 无沙箱、无控制限制，让 iflow 自由执行部署命令
# 不设置 IFLOW_sandbox，默认即为 false

if [[ -n "$1" ]]; then
  # 非交互式：直接传入 prompt
  exec iflow --yolo -m glm-5 -p "$*"
else
  # 交互式：启动 iflow 会话
  exec iflow --yolo -m glm-5
fi
