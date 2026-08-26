from __future__ import annotations

import asyncio
import sys

from alex_memory.app import AlexMemoryApp
from alex_memory.config import load_settings


def main() -> int:
    try:
        settings = load_settings()
        app = AlexMemoryApp(settings)
        if "--daemon" in sys.argv[1:]:
            return asyncio.run(app.run_daemon())
        return asyncio.run(app.run())
    except (KeyboardInterrupt, EOFError):
        return 0
    except Exception as error:
        print(f"Fatal error: {type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
