"""Fixed-effects regression with standard errors clustered by session.

Small and explicit rather than a dependency: every estimate in the settlement tests has the
same shape - security and often session fixed effects, a handful of regressors, errors
correlated across securities within a session - and the cluster adjustment is the part that
has to be right. Cross-sectional correlation on an event day is the rule rather than the
exception, and treating a thousand security observations from one expiry as a thousand
independent draws would overstate precision by an order of magnitude.

Session fixed effects matter for anything measured in returns. A monthly expiry that
happened to fall on a day of large market-wide news would otherwise contribute that news to
every security's return, and with twelve expiries a single such day dominates the estimate.
With a session effect the coefficient on an interaction is identified from differences
between securities on the same session, and the market move drops out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd


@dataclass
class Fit:
    names: List[str]
    coef: np.ndarray
    se: np.ndarray
    nobs: int
    clusters: int

    def get(self, name: str) -> Dict[str, float]:
        if name not in self.names:
            return {"coef": np.nan, "se": np.nan, "t": np.nan, "p": np.nan}
        i = self.names.index(name)
        b, s = float(self.coef[i]), float(self.se[i])
        t = b / s if s > 0 else np.nan
        from scipy import stats

        p = float(2 * stats.t.sf(abs(t), df=max(self.clusters - 1, 1))) if np.isfinite(t) else np.nan
        return {"coef": b, "se": s, "t": t, "p": p}


def _absorb(frame: pd.DataFrame, columns: List[str], effects: Sequence[str],
            tol: float = 1e-10, max_iter: int = 200) -> pd.DataFrame:
    """Remove one or more sets of fixed effects by alternating projections.

    With one set this is the ordinary within transformation. With two it converges to the
    two-way within transformation whether or not the panel is balanced.
    """
    values = frame[columns].astype(float).copy()
    for _ in range(max_iter if len(effects) > 1 else 1):
        before = values.to_numpy().copy()
        for effect in effects:
            values = values - values.groupby(frame[effect]).transform("mean")
        if len(effects) > 1 and np.max(np.abs(values.to_numpy() - before)) < tol:
            break
    return values


def fe_ols(frame: pd.DataFrame, y: str, x: List[str],
           fe: Union[None, str, Sequence[str]] = "symbol",
           cluster: str = "session") -> Optional[Fit]:
    """OLS of `y` on `x` after absorbing the `fe` effects; errors clustered on `cluster`."""
    effects = [fe] if isinstance(fe, str) else list(fe or [])
    needed = list(dict.fromkeys([y, *x, cluster, *effects]))
    work = frame[needed].replace([np.inf, -np.inf], np.nan).dropna()
    if len(work) < len(x) + 10:
        return None
    if effects:
        # Singletons carry no within variation and only inflate the observation count.
        for effect in effects:
            work = work[work.groupby(effect)[y].transform("size") > 1]
        demeaned = _absorb(work, [y, *x], effects)
        Y = demeaned[y].to_numpy()
        X = demeaned[x].to_numpy()
        absorbed = sum(work[e].nunique() for e in effects) - (len(effects) - 1)
        names = list(x)
    else:
        Y = work[y].to_numpy()
        X = np.column_stack([np.ones(len(work)), work[x].to_numpy()])
        absorbed = 0
        names = ["const", *x]

    # A regressor that the fixed effects absorb completely - a session-level indicator
    # under a session effect - is left as numerical noise by the demeaning, not as exact
    # zeros, so the test is relative to the regressor's own scale.
    scale = np.abs(work[x].to_numpy()).max(axis=0) if effects else None
    keep = np.ones(X.shape[1], dtype=bool)
    if effects:
        keep = np.sqrt((X ** 2).mean(axis=0)) > 1e-8 * np.maximum(scale, 1e-12)
    X = X[:, keep]
    names = [n for n, k in zip(names, keep) if k]
    if X.shape[1] == 0:
        return None

    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ Y
    resid = Y - X @ beta

    codes, _ = pd.factorize(work[cluster].to_numpy())
    G = codes.max() + 1
    scores = np.zeros((G, X.shape[1]))
    np.add.at(scores, codes, X * resid[:, None])
    meat = scores.T @ scores
    n, k = X.shape[0], X.shape[1] + absorbed
    correction = (G / max(G - 1, 1)) * ((n - 1) / max(n - k, 1))
    cov = correction * XtX_inv @ meat @ XtX_inv
    return Fit(names=names, coef=beta, se=np.sqrt(np.clip(np.diag(cov), 0, None)),
               nobs=int(n), clusters=int(G))


def winsorize(series: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    lo, hi = series.quantile(lower), series.quantile(upper)
    return series.clip(lo, hi)
