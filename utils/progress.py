"""Progress reporting for the long Rust stages.

nsetick does its own threading and offers no callback, so wrapping its calls in a loop to get
a progress bar would trade the parallelism that makes it fast for the comfort of a percentage.
Instead a background thread watches the output directory while the call runs: partitions
appear as they are finished, so counting them is real progress at no cost to the work.

Two shapes, because the two stages differ in what is knowable:

`track_symbols` is determinate. Book reconstruction writes one partition per symbol and the
symbol list is known up front, so the bar reports *n* of *N* and an honest estimate.

`track_bytes` is indeterminate. A parse is one pass over a compressed file whose record count
is not known until it ends, so there is no percentage to report; it shows elapsed time, output
written and the current rate, which is what tells you whether the run is progressing or stuck.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

# Watching costs filesystem calls against the same directory the writer is appending to, so
# the watcher measures its own scan and sleeps in proportion: never more than this fraction of
# wall time spent looking. A session with 1,129 partitions therefore polls far less often than
# one with six, with no threshold to tune and no way for the display to become the bottleneck.
MAX_WATCH_DUTY = 0.02

# However cheap the watcher must be, it has to look alive. Backing off proportionally is
# right for the *scan*, but a bar that has not moved for a minute is indistinguishable from a
# hung job - which is the exact question the bar exists to answer. So the scan interval is
# capped, and between scans the bar is refreshed on a short timer so the elapsed clock keeps
# running even when the count has not changed.
MAX_SCAN_INTERVAL = 10.0
REFRESH_INTERVAL = 1.0

# Set NSETICK_NO_PROGRESS=1 to suppress the bars entirely.
DISABLED = os.environ.get("NSETICK_NO_PROGRESS", "").strip() not in ("", "0", "false", "False")


def _tqdm(**kwargs):
    if DISABLED:
        return None
    try:
        from tqdm import tqdm

        return tqdm(**kwargs)
    except ImportError:
        return None


def _sleep_for(scan_secs: float, floor: float) -> float:
    """How long to wait before the next scan, given what the last one cost."""
    return min(MAX_SCAN_INTERVAL, max(floor, scan_secs / MAX_WATCH_DUTY))


def _wait_refreshing(stop: threading.Event, bar, seconds: float) -> None:
    """Wait, keeping the bar's clock visibly ticking."""
    deadline = time.monotonic() + seconds
    while not stop.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        if stop.wait(min(REFRESH_INTERVAL, remaining)):
            return
        try:
            bar.refresh()
        except Exception:
            return


def _dir_bytes(root: Path) -> int:
    """Bytes under a tree, walked with scandir.

    `Path.rglob` builds a Path object per entry and stats it separately; `os.scandir` carries
    the size in the directory entry the OS already returned, which is the difference between
    one syscall per file and several.
    """
    total = 0
    stack = [str(root)]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    try:
                        if e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                        elif e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _count_dirs(root: Path, prefix: str = "symbol=") -> int:
    """Directories whose name starts with `prefix`, anywhere under a tree."""
    n = 0
    stack = [str(root)]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if e.name.startswith(prefix):
                                n += 1
                            else:
                                stack.append(e.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return n


def _count_files(root: Path, suffix: str = ".parquet") -> int:
    """Files with a given suffix anywhere under a tree, without stat-ing any of them."""
    n = 0
    stack = [str(root)]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif e.name.endswith(suffix):
                            n += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return n


@contextmanager
def track_symbols(
    watch_dir: Path,
    total: int,
    desc: str,
    poll: float = 0.5,
) -> Iterator[None]:
    """Bar over symbols completed, counted from partition files as they land.

    Counts every `.parquet` under the staging tree rather than matching a glob. The staging
    directory is created empty for this call and holds nothing else, so a suffix test on the
    directory entry is both sufficient and cheaper than pattern matching each path.
    """
    bar = _tqdm(total=total, desc=desc, unit="sym", ncols=100, leave=True)
    if bar is None:
        yield
        return

    stop = threading.Event()

    def watch():
        seen = 0
        while not stop.is_set():
            t0 = time.perf_counter()
            n = min(_count_files(watch_dir), total)
            cost = time.perf_counter() - t0
            if n > seen:
                bar.update(n - seen)
                seen = n
            _wait_refreshing(stop, bar, _sleep_for(cost, poll))
        # Snap to complete: the final partitions are written as the call returns, so the last
        # poll can miss them and leave the bar short of the total it just finished.
        if seen < total:
            bar.update(total - seen)

    t = threading.Thread(target=watch, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join(timeout=2.0)
        bar.close()


@contextmanager
def track_bytes(
    watch_dir: Path,
    desc: str,
    poll: float = 2.0,
    expected_bytes: Optional[int] = None,
) -> Iterator[None]:
    """Indeterminate display: elapsed, output written, and rate.

    `expected_bytes` turns it determinate when a reasonable estimate exists - for a reparse of
    a session whose previous output size is known, say - but it is deliberately optional,
    because a guessed denominator that turns out wrong is worse than no denominator.

    Partition count is shown alongside the byte total because bytes stay at zero for the first
    half-minute of a large parse: the writer buffers roughly a megabyte per partition before
    committing a row group, so with a thousand partitions nothing reaches disk for some time.
    A display reading "0.00 written" during that window looks broken. Partition directories
    are created as each symbol is first seen, so they start moving immediately.
    """
    bar = _tqdm(
        total=expected_bytes, desc=desc, unit="B", unit_scale=True, ncols=100,
        leave=True, bar_format=None if expected_bytes else
        # {postfix} must appear here or set_postfix_str writes into a field the format
        # never renders, which is what silently hid the partition count.
        "{desc}: {n_fmt} written{postfix} [{elapsed}, {rate_fmt}]",
    )
    if bar is None:
        yield
        return

    stop = threading.Event()

    def watch():
        seen = 0
        while not stop.is_set():
            t0 = time.perf_counter()
            n = _dir_bytes(watch_dir)
            parts = _count_dirs(watch_dir)
            cost = time.perf_counter() - t0
            if parts:
                bar.set_postfix_str(f"{parts:,} partitions", refresh=False)
            if n > seen:
                bar.update(n - seen)
                seen = n
            _wait_refreshing(stop, bar, _sleep_for(cost, poll))

    t = threading.Thread(target=watch, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join(timeout=3.0)
        bar.close()


class Elapsed:
    """Wall time for a step, for logging when a bar is not wanted."""

    def __init__(self) -> None:
        self.t0 = time.time()

    @property
    def secs(self) -> float:
        return time.time() - self.t0

    def __str__(self) -> str:
        s = self.secs
        return f"{s:.1f}s" if s < 90 else f"{s / 60:.1f}m"
