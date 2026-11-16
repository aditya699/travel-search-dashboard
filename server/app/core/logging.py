"""One logging setup for the CLI and the API."""

from __future__ import annotations

import logging


def setup_logging(level: str = "INFO") -> None:
    """Plain, timestamped log lines on stderr."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # httpx logs every request at INFO, which drowns the pipeline's own lines.
    logging.getLogger("httpx").setLevel(logging.WARNING)
