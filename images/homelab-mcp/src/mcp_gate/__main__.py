import logging
import os

import uvicorn

from mcp_gate.server import create_app

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
uvicorn.run(create_app(), host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8000")), log_level="info")  # noqa: S104
