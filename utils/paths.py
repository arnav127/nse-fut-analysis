"""Where each layer's data lives, and the two date spellings the pipeline uses.

Sessions are named the way NSE names its files - `DDMMYYYY`, as in `CASH_Orders_27012022` -
and that string is the pipeline's session identifier end to end. Timestamps inside the data
are real timestamps, so anything derived from them is ISO (`2022-01-27`). Both spellings are
carried on every enriched row: `session` for joining back to a file or to the expiry
calendar, `trade_date` for reading and for anything ordered by date. Keeping both is what
removes the old defect where a stage compared an ISO `trade_date` against a `DDMMYYYY`
expiry list and matched nothing, silently.
"""

from __future__ import annotations

import glob
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import List

from config.settings import (
    CLOB_DATA_DIR,
    ENRICHED_DATA_DIR,
    PARSED_DATA_DIR,
    RAW_DATA_DIR,
)

SESSION_FMT = "%d%m%Y"


def session_to_date(session: str) -> date:
    """`27012022` -> `date(2022, 1, 27)`."""
    return datetime.strptime(session, SESSION_FMT).date()


def session_to_iso(session: str) -> str:
    """`27012022` -> `2022-01-27`."""
    return session_to_date(session).isoformat()


def iso_to_session(iso: str) -> str:
    """`2022-01-27` -> `27012022`."""
    return date.fromisoformat(iso).strftime(SESSION_FMT)


def raw_files(file_prefix: str, session: str) -> List[str]:
    """Raw files for one feed and session, oldest name first.

    `.trg` trigger files sit beside the data with a matching stem and contain a record count,
    not records; including one would feed control data to the parser.
    """
    pattern = (Path(RAW_DATA_DIR) / f"{file_prefix}_{session}*.DAT*").as_posix()
    return sorted(p for p in glob.glob(pattern) if not p.endswith(".trg"))


def parsed_dir(category: str, session: str) -> Path:
    return PARSED_DATA_DIR / category / f"date={session}"


def enriched_dir(category: str, session: str) -> Path:
    return ENRICHED_DATA_DIR / category / f"date={session}"


def clob_dir(session: str) -> Path:
    return CLOB_DATA_DIR / f"date={session}"


def has_partitions(directory: Path) -> bool:
    """True when a stage has already written symbol partitions here.

    Tests for a partition directory rather than for the directory itself, because every
    stage creates its output directory before doing any work - so the directory existing
    proves only that the stage started.
    """
    return directory.is_dir() and any(directory.glob("symbol=*"))


def promote_hive_partitions(staging: Path, out_dir: Path) -> int:
    """Lift nsetick's `symbol=*` partitions out of its hive tree into `out_dir`.

    nsetick nests its output under `segment=/kind=/date=`, which is the right shape for a
    lake holding every segment and feed together. This pipeline keeps one directory per
    stage output instead, so the symbol partitions are moved up and the scaffolding
    discarded. The tree is searched rather than reconstructed from the layout name: the
    `kind=` segment differs between products (`orders`, `book_snapshots`), and a wrong guess
    finds nothing and silently reports an empty stage.

    Returns the number of partitions moved.
    """
    roots = sorted({p.parent for p in staging.glob("segment=*/**/symbol=*") if p.is_dir()})
    moved = 0
    for root in roots:
        for sym_dir in root.glob("symbol=*"):
            dest = out_dir / sym_dir.name
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            shutil.move(str(sym_dir), str(dest))
            moved += 1

    for manifest in staging.glob("_manifest*"):
        dest = out_dir / manifest.name
        dest.unlink(missing_ok=True)
        shutil.move(str(manifest), str(dest))
    return moved


def parquet_glob(root: Path) -> str:
    """Recursive parquet pattern for a layer root, in the form DuckDB wants."""
    return (root / "**" / "*.parquet").as_posix()
