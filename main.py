"""kb_mp 后端入口：仅启动 uvicorn。"""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "app.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
