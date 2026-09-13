"""Recorded quantities, and where each one came from.

Every number the manuscript states is written here first, by the code that computes it, and
reaches LaTeX only as a macro. Nothing is typed into the document by hand. That is not
tidiness: a hand-typed figure is correct on the day it is typed and silently wrong after the
next pipeline change, and there is no way to tell which by reading the document.

Each entry carries the value, its unit, and the module that produced it. Alongside them a
`meta` block records the commit of both repositories, the library versions, the host, and a
fingerprint of every input file, so a referee asking "where does this number come from" gets
an answer rather than an assurance.

    from utils.provenance import Run

    with Run("stage5.b4") as run:
        run.record("impact.kyle_lambda", 0.00048, "rupees per share",
                   "regression of minute price change on tick-rule signed volume")

The store is a single JSON file, rewritten atomically. Stages run one at a time, so there is
no concurrent writer to coordinate with; the atomic replace is against an interrupted run
leaving a truncated file that the next stage would fail to parse.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import RAW_DATA_DIR, RESULTS_DIR  # noqa: E402

METRICS_PATH = Path(RESULTS_DIR) / "metrics.json"

# The repositories whose code determines the numbers. nsetick is included because a change
# to the parser or the book engine changes the data every later stage sees.
CODE_REPOSITORIES = {
    "ProjectCourse": PROJECT_ROOT,
    "nsetick": PROJECT_ROOT.parent / "nsetick",
}


def _git(repo: Path, *args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", "-C", str(repo), *args],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def _repo_state(repo: Path) -> Dict[str, Any]:
    if not (repo / ".git").exists():
        return {"available": False}
    status = _git(repo, "status", "--porcelain")
    return {
        "available": True,
        "commit": _git(repo, "rev-parse", "HEAD"),
        "branch": _git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        # A dirty tree means the recorded commit does not describe the code that ran, which
        # is exactly the situation a reproduction attempt needs to be warned about.
        "dirty": bool(status),
        # Porcelain lines are two status characters then the path, but the separator is one
        # space for some states and two for others, so the path is taken by stripping rather
        # than by a fixed offset - slicing at a constant chopped the first character off
        # whichever form was shorter.
        "dirty_files": [line[2:].strip() for line in status.splitlines()][:20] if status else [],
    }


def _library_versions() -> Dict[str, str]:
    versions = {"python": platform.python_version()}
    for name in ("nsetick", "duckdb", "pandas", "numpy", "scipy", "statsmodels",
                 "pyarrow", "matplotlib"):
        try:
            versions[name] = __import__(name).__version__
        except Exception:
            versions[name] = "not installed"
    return versions


def _input_manifest() -> Dict[str, Any]:
    """Size and modification time of every raw file.

    Not a content hash: these are gigabyte-scale compressed files and hashing all of them
    costs more than the whole pipeline. Size plus mtime distinguishes a re-download or a
    different vintage of the same session, which is the failure this guards against.
    """
    files = {}
    for path in sorted(Path(RAW_DATA_DIR).glob("*.DAT*")):
        try:
            stat = path.stat()
        except OSError:
            continue
        files[path.name] = {
            "bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        }
    return {"file_count": len(files), "total_bytes": sum(f["bytes"] for f in files.values()),
            "files": files}


def load_metrics() -> Dict[str, Any]:
    if not METRICS_PATH.exists():
        return {}
    try:
        return json.loads(METRICS_PATH.read_text(encoding="utf-8")).get("metrics", {})
    except (OSError, json.JSONDecodeError):
        return {}


def load_meta() -> Dict[str, Any]:
    if not METRICS_PATH.exists():
        return {}
    try:
        return json.loads(METRICS_PATH.read_text(encoding="utf-8")).get("meta", {})
    except (OSError, json.JSONDecodeError):
        return {}


def _write(payload: Dict[str, Any]) -> None:
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = METRICS_PATH.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    os.replace(temp, METRICS_PATH)


def refresh_meta() -> Dict[str, Any]:
    """Re-record the environment block, keeping whatever metrics are already stored."""
    meta = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(),
        "platform": platform.platform(),
        "code": {name: _repo_state(path) for name, path in CODE_REPOSITORIES.items()},
        "libraries": _library_versions(),
        "inputs": _input_manifest(),
    }
    _write({"meta": meta, "metrics": load_metrics()})
    return meta


def reset() -> None:
    """Drop every recorded metric and start a fresh environment block.

    Called once at the start of a reporting run. Without it a metric whose recorder was
    deleted would persist in the store indefinitely and keep appearing in the manuscript,
    which is the hand-typed-number problem with extra steps.
    """
    _write({"meta": {}, "metrics": {}})
    refresh_meta()


class Run:
    """Records metrics under one source module."""

    def __init__(self, source: str) -> None:
        self.source = source
        self._metrics: Dict[str, Any] = {}

    def record(self, key: str, value: Any, unit: str = "", note: str = "") -> Any:
        """Store one quantity. Returns the value, so a computation can record in passing."""
        if value is None:
            return None
        # NaN survives JSON round-tripping as the literal NaN, which is not valid JSON and
        # would become a macro reading "nan" in the manuscript. Dropped instead.
        if isinstance(value, float) and value != value:
            return None
        self._metrics[key] = {
            "value": value,
            "unit": unit,
            "note": note,
            "source": self.source,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        return value

    def flush(self) -> None:
        if not self._metrics:
            return
        payload = {"meta": load_meta() or refresh_meta(), "metrics": {**load_metrics(), **self._metrics}}
        _write(payload)
        self._metrics = {}

    def __enter__(self) -> "Run":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        # Flushed even on failure: the metrics recorded before the error are real, and
        # discarding them would make a partial run look like it computed nothing.
        self.flush()
        return False
