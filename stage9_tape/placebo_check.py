"""Where the placebo stocks sit in the market: Nifty 500 membership and turnover rank.

Membership is checked against the Nifty 500 list of October 2022 (an archived copy of the
exchange's file), and, for stability, against the lists of July 2020 and February 2024. Turnover rank
is among all equities traded on the order book sample's sessions.

Output: data/results/s17_placebo_check.csv (one row per universe stock) and a summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import RESULTS_DIR  # noqa: E402

EXTERNAL = PROJECT_ROOT / "data" / "external"


def main() -> None:
    universe = json.loads((PROJECT_ROOT / "config" / "universe_2022.json").read_text())
    group = {s: g for g, members in universe["groups"].items() for s in members}
    xs = pd.read_csv(Path(RESULTS_DIR) / "s15_cash_cross_section.csv")
    xs["rank"] = xs.turnover_cr.rank(ascending=False, method="min").astype(int)
    lists = {name: set(pd.read_csv(EXTERNAL / f"nifty500_{name}.csv").Symbol)
             for name in ("2022oct", "2020", "2024", "current")}
    fo = set((PROJECT_ROOT / "config" / "fo_underlyings_2022.txt").read_text().split())
    frame = pd.DataFrame({"symbol": list(group), "group": [group[s] for s in group]})
    frame = frame.merge(xs[["symbol", "turnover_cr", "rank", "price"]], on="symbol", how="left")
    for name, members in lists.items():
        frame[f"n500_{name}"] = frame.symbol.isin(members)
    frame["n500_both"] = frame.n500_2020 & frame.n500_2024
    frame["n500_either"] = frame.n500_2020 | frame.n500_2024
    frame["fo"] = frame.symbol.isin(fo)
    frame.to_csv(Path(RESULTS_DIR) / "s17_placebo_check.csv", index=False)

    summary = frame.groupby("group").agg(
        stocks=("symbol", "size"), n500_2022=("n500_2022oct", "sum"),
        n500_2020=("n500_2020", "sum"), n500_2024=("n500_2024", "sum"),
        n500_both=("n500_both", "sum"), n500_either=("n500_either", "sum"),
        rank_median=("rank", "median"), rank_min=("rank", "min"), rank_max=("rank", "max"),
        turnover_median_cr=("turnover_cr", "median"))
    summary["market_stocks"] = len(xs)
    summary.to_csv(Path(RESULTS_DIR) / "s17_placebo_summary.csv")
    print(summary.round(1).to_string())
    print("placebo with F&O (should be 0):", int(frame[frame.group == "placebo"].fo.sum()))


if __name__ == "__main__":
    main()
