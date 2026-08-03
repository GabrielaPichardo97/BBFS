"""Small logging setup shared by future commands."""

from __future__ import annotations

import logging


def configure_logging(level: str) -> None:
    """Configure deterministic process-local console logging."""
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
