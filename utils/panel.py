"""Fixed-effects regression with standard errors clustered by session.

Small and explicit rather than a dependency: every estimate in the settlement tests has the
same shape - security fixed effects, a handful of regressors, errors correlated across
securities within a session - and the cluster adjustment is the part that has to be right.
Cross-sectional correlation on an event day is the rule rather than the exception, and
treating a thousand security observations from one expiry as a thousand independent draws
would overstate precision by an order of magnitude.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

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
        i = self.names.index(name)
        b, s = float(self.coef[i]), float(self.se[i])
        t = b / s if s > 0 else np.nan
        from scipy import stats

        p = float(2 * stats.t.sf(abs(t), df=max(self.clusters - 1, 1))) if np.isfinite(t) else np.nan
        return {"coef": b, "se": s, "t": t, "p": p}


def _demean(frame: pd.DataFrame, columns: List[str], by: str) -> pd.DataFrame:
    return frame[columns] - frame.groupby(by)[columns].transform("mean")


def fe_ols(frame: pd.DataFrame, y: str, x: List[str], fe: Optional[str] = "symbol",
           cluster: str = "session") -> Optional[Fit]:
    """OLS of `y` on `x` after removing `fe` means; errors clustered on `cluster`."""
    work = frame[[y, *x, cluster] + ([fe] if fe else [])].replace([np.inf, -np.inf], np.nan)
    work = work.dropna()
    if len(work) < len(x) + 10:
        return None
    if fe:
        # Singletons carry no within variation and only inflate the observation count.
        work = work[work.groupby(fe)[y].transform("size") > 1]
        demeaned = _demean(work, [y, *x], fe)
        Y = demeaned[y].to_numpy()
        X = demeaned[x].to_numpy()
        absorbed = work[fe].nunique()
    else:
        Y = work[y].to_numpy()
        X = np.column_stack([np.ones(len(work)), work[x].to_numpy()])
        absorbed = 0
    keep = np.abs(X).sum(axis=0) > 0
    if not keep.all():
        X = X[:, keep]
    names = ([] if fe else ["const"]) + list(x)
    names = [n for n, k in zip(names, keep) if k]

    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ Y
    resid = Y - X @ beta

    groups = work[cluster].to_numpy()
    codes, _ = pd.factorize(groups)
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
