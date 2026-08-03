"""Run the complete BBFS demonstration without a notebook.

Usage: ``python scripts/run_demo.py --fresh --yes``.
"""

from __future__ import annotations

import sys

from baby_first_steps_medallion.cli import main

if __name__ == "__main__":
    sys.argv.insert(1, "demo")
    main()
