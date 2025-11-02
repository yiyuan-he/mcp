"""Entry point for running evals as a module: python -m evals."""

import asyncio
import sys
from evals.core.cli import main


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nInterrupted by user')
        sys.exit(0)
