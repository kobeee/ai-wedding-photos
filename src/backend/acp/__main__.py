"""ACP 包入口 — python -m acp 启动 ACP Server。"""

import logging

from acp.server import server
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

logger.info("Starting ACP Server on port %d ...", settings.acp_port)
logger.info("Registered %d agent(s): %s",
            len(server.agents),
            [getattr(a, 'name', '?') for a in server.agents])

server.run(host="0.0.0.0", port=settings.acp_port)
