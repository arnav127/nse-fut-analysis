"""Stage 1: raw NSE fixed-width files into symbol-partitioned Parquet, via nsetick.

Replaces the DuckDB `read_csv` + `SUBSTRING` parser. That approach had three problems
beyond speed, all of which produced output that looked correct:

  * It re-declared the byte offsets locally, so they could drift from the specification -
    and did, repeatedly.
  * It pulled the symbol out with `REGEXP_EXTRACT(..., '[A-Z0-9-]+')`, which truncates
    every symbol containing an ampersand. `M&M` became `M`, `J&KBANK` became `J`. Those
    rows then matched no universe entry and vanished from the sample without a warning.
  * It read fixed-width records through a CSV reader, which applies quote handling to a
    format that has no quoting.

nsetick decodes by the versioned layout, selecting the record version by date and checking
it against the observed record length, strips the 'b' padding, scales prices and converts
jiffies to real timestamps in the single decode pass.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import nsetick

from config.categories import CATEGORIES, Category
from config.settings import NSETICK_THREADS, TARGET_SYMBOLS
from utils.logger import setup_logger
from utils.paths import has_partitions, parsed_dir, promote_hive_partitions, raw_files
from utils.progress import track_bytes

logger = setup_logger("TickParser", "stage1_parse.log")


def _where_clause(category: Category, symbols: Optional[List[str]]) -> str:
    """The feed's own filter, narrowed to a symbol list when one is given.

    nsetick validates this against the layout before reading a byte, so a misspelled field
    fails immediately rather than yielding an empty result that looks like a quiet session.
    """
    if not symbols:
        return category.where
    quoted = ", ".join(f"'{s}'" for s in symbols)
    return f"{category.where} and symbol in ({quoted})"


def parse_category(
    session: str,
    category_name: str,
    symbols: Optional[List[str]] = None,
    force: bool = False,
) -> Optional[Path]:
    """Parse one feed for one session. Returns the output directory, or None if skipped."""
    category = CATEGORIES[category_name]
    out_dir = parsed_dir(category_name, session)

    if has_partitions(out_dir) and not force:
        logger.info(f"[SKIP] {category_name} {session} already parsed ({out_dir})")
        return out_dir

    files = raw_files(category.file_prefix, session)
    if not files:
        msg = f"no raw file matching {category.file_prefix}_{session}*"
        if category.required:
            raise FileNotFoundError(msg)
        logger.info(f"[ABSENT] optional feed {category_name} {session}: {msg}")
        return None

    if len(files) > 1 and not category.multipart:
        # CM ships one file per session. More than one means either a re-download sitting
        # beside the original or a feed change; either way parsing both duplicates rows,
        # and silently doubling a session's volume is worse than stopping.
        raise RuntimeError(
            f"{len(files)} files match {category.file_prefix}_{session}*, but this feed is "
            f"not multi-part: {files}"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    # Clear anything already in this session's directory. The previous parser wrote a single
    # flat `data.parquet` here with different column names and units; left in place beside
    # the new partitions it would be a second schema under the same root, which is the kind
    # of leftover a recursive glob picks up silently.
    for stale in out_dir.iterdir():
        if stale.is_dir():
            shutil.rmtree(stale, ignore_errors=True)
        else:
            stale.unlink(missing_ok=True)

    staging = out_dir / "_staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)

    where = _where_clause(category, symbols)
    universe = "all symbols" if not symbols else f"{len(symbols)} symbols"
    logger.info(f"[PARSE] {category_name} {session} ({universe}, {len(files)} file(s))")

    started = time.time()
    reports = []
    try:
        for part, path in enumerate(files, 1):
            label = f"parse {category_name} {session}"
            if len(files) > 1:
                label += f" [{part}/{len(files)}]"
            with track_bytes(staging, label):
                reports.append(
                    nsetick.parse(
                        input=path,
                        out=staging.as_posix(),
                        layout=category.layout,
                        where=where,
                        partition_by="symbol",
                        compression="snappy",
                        threads=NSETICK_THREADS,
                        note=f"ProjectCourse stage1 {category_name} {session}",
                    )
                )
        partitions = promote_hive_partitions(staging, out_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    emitted = sum(r["rows_emitted"] for r in reports)
    read = sum(r["rows_read"] for r in reports)
    malformed = sum(r["rows_malformed"] for r in reports)

    (out_dir / "symbols.json").write_text(
        json.dumps(sorted(p.name.split("=", 1)[1] for p in out_dir.glob("symbol=*")), indent=2),
        encoding="utf-8",
    )

    logger.info(
        f"[DONE] {category_name} {session}: {emitted:,} of {read:,} rows kept across "
        f"{partitions} symbols in {time.time() - started:.1f}s"
    )
    if malformed:
        logger.warning(f"[MALFORMED] {malformed:,} undecodable records in {category_name} {session}")
    if emitted == 0:
        logger.warning(f"[EMPTY] {category_name} {session} matched no rows for filter: {where}")
    return out_dir


def parse_session(session: str, symbols: Optional[List[str]] = None, force: bool = False) -> None:
    """Parse all four feeds for one session, reporting rather than aborting on failure."""
    for name in CATEGORIES:
        try:
            parse_category(session, name, symbols=symbols, force=force)
        except FileNotFoundError as exc:
            logger.error(f"[MISSING] {name} {session}: {exc}")
        except Exception as exc:  # one bad feed should not abandon the other three
            logger.error(f"[FAILED] {name} {session}: {exc}")


if __name__ == "__main__":
    import argparse

    from config.settings import ALL_TARGET_DATES

    ap = argparse.ArgumentParser(description="Stage 1: parse NSE tick files with nsetick")
    ap.add_argument("--date", help="single session in DDMMYYYY form")
    ap.add_argument("--universe-only", action="store_true",
                    help="restrict to config.settings.TARGET_SYMBOLS")
    ap.add_argument("--force", action="store_true", help="reparse sessions already present")
    args = ap.parse_args()

    for s in [args.date] if args.date else ALL_TARGET_DATES:
        parse_session(s, symbols=TARGET_SYMBOLS if args.universe_only else None, force=args.force)
