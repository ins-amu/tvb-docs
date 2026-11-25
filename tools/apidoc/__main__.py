"""Package runner for `python -m tools.apidoc`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
