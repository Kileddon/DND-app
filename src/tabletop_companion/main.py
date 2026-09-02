from __future__ import annotations

import uvicorn

from tabletop_companion.api.app import create_app
from tabletop_companion.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
