"""DuckDB connections that respect the budget this process was given.

DuckDB sizes its memory limit and thread count from the machine unless told otherwise, which
is right on a workstation and wrong everywhere else. Under a scheduler it sees the node, not
the allocation; with several workers running at once it sees the whole machine, not its
share. Both cases end the same way, as an allocation failure some hours into a run.

Every connection in the pipeline goes through here so the budget is applied in one place
rather than remembered at each of a dozen call sites.
"""

from __future__ import annotations

import contextlib
from typing import Iterator, Optional

import duckdb

from utils.resources import available_cpus, available_memory_mb


@contextlib.contextmanager
def connect(memory_mb: Optional[int] = None,
            threads: Optional[int] = None,
            temp_directory: Optional[str] = None) -> Iterator[duckdb.DuckDBPyConnection]:
    """A connection limited to `memory_mb` and `threads`, defaulting to this process's share.

    The spill directory is worth setting on a cluster. DuckDB spills to the working directory
    by default, which on a shared filesystem is both slow and, on some systems, quota-limited
    in a way that surfaces as a confusing write error rather than as a disk-full one.
    """
    memory_mb = memory_mb or available_memory_mb()
    threads = threads or available_cpus()

    connection = duckdb.connect()
    try:
        connection.execute(f"SET memory_limit='{int(memory_mb)}MB'")
        connection.execute(f"SET threads={int(threads)}")
        if temp_directory:
            connection.execute(f"SET temp_directory='{temp_directory}'")
        yield connection
    finally:
        connection.close()
