import time

import uvicorn

from app.core.config import settings
from app.main import app


if __name__ == "__main__":
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=settings.host,
            port=settings.port,
            log_level="info",
        )
    )
    app.state.server = server
    app.state.started_at = time.time()
    server.run()
