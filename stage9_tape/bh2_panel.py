"""BH2 as a panel regression with stock fixed effects.

One observation per stock and session of the order book sample (12 expiries and the day before
each), for the settlement window and for the rest of the session. The log of the quoted spread
and of displayed depth is regressed on an expiry indicator with stock and month fixed effects,
separately for each group, and in a pooled regression in which the expiry effect may differ
between stocks with derivatives and placebo stocks (difference in differences, with stock and
session fixed effects). A second set adds the log of realised variance as a control.

Standard errors are clustered by stock (session fixed effects absorb the market, and with
twenty-four sessions clustering by session would leave too few clusters).

Output: data/results/s16_bh2_panel.csv.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import EXPIRY_CONTROL_PAIRS, RESULTS_DIR  # noqa: E402
from utils.panel import fe_ols  # noqa: E402

WINDOW = (345, 375)
DAY = (15, 345)
PAIR_OF = {c: e for e, c in EXPIRY_CONTROL_PAIRS} | {e: e for e, _ in EXPIRY_CONTROL_PAIRS}


def stock_sessions(book: pd.DataFrame, lo: int, hi: int) -> pd.DataFrame:
    part = book[(book.minute >= lo) & (book.minute < hi)]
    agg = part.groupby(["symbol", "group", "session", "is_expiry"]).agg(
        spread=("spread_bps", "mean"), depth=("depth_cr", "mean"),
        rv=("rv_bps2", "mean")).reset_index()
    agg = agg[(agg.spread > 0) & (agg.depth > 0) & (agg.rv > 0)].copy()
    agg["log_spread"] = 100 * np.log(agg.spread)
    agg["log_depth"] = 100 * np.log(agg.depth)
    agg["log_rv"] = 100 * np.log(agg.rv)
    agg["expiry"] = agg.is_expiry.astype(float)
    agg["month"] = agg.session.map(PAIR_OF)
    agg["fo"] = (agg.group != "placebo").astype(float)
    agg["expiry_x_fo"] = agg.expiry * agg.fo
    agg["fe_month"] = agg.symbol + "_" + agg.month
    return agg


def run() -> pd.DataFrame:
    book = pd.read_parquet(Path(RESULTS_DIR) / "book_profile.parquet")
    rows = []
    for part, (lo, hi) in (("window", WINDOW), ("before window", DAY)):
        frame = stock_sessions(book, lo, hi)
        for y in ("log_spread", "log_depth"):
            for control in (False, True):
                extra = ["log_rv"] if control else []
                # Within each group: stock and month effects, expiry against the day before.
                for g in ("liquid", "illiquid", "placebo"):
                    sub = frame[frame.group == g]
                    fit = fe_ols(sub, y, ["expiry", *extra], fe=("symbol", "month"),
                                 cluster="symbol")
                    rows.append({"part": part, "y": y, "vol_control": control, "sample": g,
                                 "term": "expiry", **fit.get("expiry"), "nobs": fit.nobs,
                                 "clusters": fit.clusters})
                # Pooled: stock and session effects; the expiry effect of F&O stocks over and
                # above the placebo group.
                fit = fe_ols(frame, y, ["expiry_x_fo", *extra], fe=("symbol", "session"),
                             cluster="symbol")
                rows.append({"part": part, "y": y, "vol_control": control, "sample": "did",
                             "term": "expiry_x_fo", **fit.get("expiry_x_fo"),
                             "nobs": fit.nobs, "clusters": fit.clusters})
    out = pd.DataFrame(rows)
    out.to_csv(Path(RESULTS_DIR) / "s16_bh2_panel.csv", index=False)
    return out


if __name__ == "__main__":
    with pd.option_context("display.width", 200):
        print(run().round(3).to_string(index=False))
