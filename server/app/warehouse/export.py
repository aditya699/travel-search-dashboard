"""Export the star schema for Power BI: one CSV and one Parquet file per table.

Power BI Desktop reads the folder through the Power Query script in
``powerbi/load_tables.pq``. The views go to ``views/`` for anyone who prefers Excel
or another BI tool.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from app.core.config import Settings
from app.core.errors import AppError
from app.warehouse.build import TABLES, VIEWS

logger = logging.getLogger(__name__)


def export(settings: Settings) -> list[Path]:
    if not settings.warehouse_path.exists():
        raise AppError("No warehouse yet. Run `python -m app.cli build` first.")
    out = settings.export_dir
    (out / "views").mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    con = duckdb.connect(str(settings.warehouse_path), read_only=True)
    try:
        for name in TABLES:
            for ext, options in (("csv", "HEADER, DELIMITER ','"), ("parquet", "FORMAT PARQUET")):
                path = out / f"{name}.{ext}"
                con.execute(f"COPY (SELECT * FROM {name}) TO '{path.as_posix()}' ({options})")
                written.append(path)
        for name in VIEWS:
            path = out / "views" / f"{name}.csv"
            con.execute(f"COPY (SELECT * FROM {name}) TO '{path.as_posix()}' (HEADER)")
            written.append(path)
    finally:
        con.close()
    logger.info("Exported %d files to %s", len(written), out)
    return written
