"""Derive the list of derivatives underlyings from the derivatives trade tape.

The universe builder needs to know which securities had an expiring contract. A list
downloaded from the exchange today describes today; the derivatives trade files describe
2022. A security counts as a derivatives underlying when its stock future traded on every
session for which the derivatives files are held, and as having no derivative when neither a
stock future nor a stock option on it traded on any of them.

Securities in between - futures on some sessions and not others, which is what an entry to or
exit from the derivatives segment during the year looks like - are listed separately and kept
out of both the derivative groups and the placebo pool.

    python scripts/fo_from_tape.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import duckdb  # noqa: E402

from config.settings import ALL_TARGET_DATES  # noqa: E402
from utils.paths import parsed_dir  # noqa: E402

CONFIG_DIR = PROJECT_ROOT / "config"
FO_LIST = CONFIG_DIR / "fo_underlyings_2022.txt"
FO_PARTIAL = CONFIG_DIR / "fo_partial_2022.txt"


def main() -> int:
    sessions = [s for s in ALL_TARGET_DATES if any(parsed_dir("fao_trades", s).glob("symbol=*"))]
    if not sessions:
        raise SystemExit("no parsed derivatives trades; parse fao_trades first")
    counts = {}
    with duckdb.connect() as conn:
        for s in sessions:
            pattern = (parsed_dir("fao_trades", s) / "symbol=*" / "*.parquet").as_posix()
            for symbol, instrument in conn.execute(f"""
                    SELECT DISTINCT symbol, instrument
                    FROM read_parquet('{pattern}', hive_partitioning = true)""").fetchall():
                counts.setdefault(symbol, {}).setdefault(instrument, set()).add(s)

    full = sorted(k for k, v in counts.items() if len(v.get("FUTSTK", ())) == len(sessions))
    partial = sorted(k for k in counts if k not in full)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = [
        "# Derivatives underlyings in 2022, derived from the derivatives trade files.",
        f"# A stock future traded on every one of {len(sessions)} sessions: "
        f"{', '.join(sessions)}.",
        f"# Written by scripts/fo_from_tape.py on {stamp}. Do not edit by hand.",
    ]
    FO_LIST.write_text("\n".join(header + full) + "\n", encoding="utf-8")
    FO_PARTIAL.write_text("\n".join([
        "# Traded in the derivatives segment on some held sessions but not all of them.",
        "# Excluded from the derivative groups and from the placebo pool.",
    ] + partial) + "\n", encoding="utf-8")
    print(f"{len(full)} underlyings on every session, {len(partial)} on some; "
          f"wrote {FO_LIST.name} and {FO_PARTIAL.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
