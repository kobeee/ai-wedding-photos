"""ACP Server — 将 AI 婚纱摄影管线暴露为可发现的 Agent。"""

import logging

from acp_sdk.server import Server

from config import settings

logger = logging.getLogger(__name__)

server = Server()

# 导入注册 agents（副作用注册）
from acp.agents import photographer, makeup, inspector  # noqa: F401, E402
