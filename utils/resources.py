"""What this process is actually allowed to use, not what the machine has.

On a workstation the two are the same. On a cluster they are not, and the difference is the
usual cause of a job being killed hours in: the node has 512 GB and 128 cores, the allocation
is 64 GB and 32 cores, and every library that sizes itself from `os.cpu_count()` or from
`/proc/meminfo` cheerfully helps itself to the node.

Both tools this pipeline drives do exactly that. nsetick sizes its memory limit from total
system memory - measured at roughly a quarter of it - and DuckDB defaults to a large fraction
of the same number. Run four of either concurrently and the arithmetic does not work: four
workers each claiming a quarter of the node's memory is the whole node, and four claiming
sixty per cent of it is nearly two and a half times what exists. Neither will notice until
the allocator fails.

So the budget is resolved here, once, and divided explicitly among workers.

Resolution order, most specific first:

  1. `PIPELINE_MEMORY_MB` / `PIPELINE_CPUS` - an operator override, which is also the escape
     hatch when the detection below is wrong.
  2. The scheduler's own variables (SLURM today; others follow the same shape).
  3. The cgroup limit, which is what the kernel will actually enforce and therefore what
     matters if the scheduler variables are absent.
  4. The machine's totals, for a workstation.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Left for the operating system, page cache and the parent process. The page cache matters
# here: the stages read what the previous stage wrote, and squeezing it out to give a worker
# a larger heap trades a cached read for a disk read.
RESERVE_FRACTION = 0.20

# Used when nothing can be detected. Low enough not to provoke an out-of-memory kill on a
# small machine; a real allocation will almost always be found instead.
FALLBACK_MEMORY_MB = 8192


def _int_env(name: str) -> Optional[int]:
    value = os.environ.get(name)
    if not value:
        return None
    try:
        return int(float(value.strip().rstrip("KMGkmg")))
    except ValueError:
        return None


def _cgroup_memory_mb() -> Optional[int]:
    """The limit the kernel will enforce, from cgroup v2 then v1."""
    for path, unlimited in ((Path("/sys/fs/cgroup/memory.max"), "max"),
                            (Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"), None)):
        try:
            raw = path.read_text().strip()
        except OSError:
            continue
        if unlimited is not None and raw == unlimited:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        # cgroup v1 reports an absurd number rather than a flag when unlimited.
        if value <= 0 or value >= 1 << 62:
            continue
        return value // (1024 * 1024)
    return None


def _system_memory_mb() -> Optional[int]:
    try:
        import psutil

        return int(psutil.virtual_memory().total // (1024 * 1024))
    except Exception:
        pass
    try:
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // (1024 * 1024))
    except (AttributeError, ValueError, OSError):
        return None


def available_memory_mb() -> int:
    """Memory this process may use, after reserving headroom for the system."""
    override = _int_env("PIPELINE_MEMORY_MB")
    if override:
        return override

    total = None
    per_node = _int_env("SLURM_MEM_PER_NODE")
    if per_node:
        total = per_node
    else:
        per_cpu = _int_env("SLURM_MEM_PER_CPU")
        if per_cpu:
            total = per_cpu * available_cpus()
    if total is None:
        total = _cgroup_memory_mb()
    if total is None:
        total = _system_memory_mb()
    if total is None:
        return FALLBACK_MEMORY_MB
    return max(1024, int(total * (1.0 - RESERVE_FRACTION)))


def available_cpus() -> int:
    """Cores this process may use.

    `sched_getaffinity` rather than `cpu_count`, because a cluster pins a job to a subset of
    the node's cores and `cpu_count` reports the node.
    """
    override = _int_env("PIPELINE_CPUS")
    if override:
        return max(1, override)
    slurm = _int_env("SLURM_CPUS_PER_TASK") or _int_env("SLURM_JOB_CPUS_PER_NODE")
    if slurm:
        return max(1, slurm)
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except AttributeError:
        return max(1, os.cpu_count() or 1)


def worker_budget(jobs: int) -> tuple:
    """Memory in MB and threads for each of `jobs` concurrent workers.

    Dividing rather than letting each worker size itself is the entire point of this module.
    Both numbers are floored at something usable: a worker given 512 MB or zero threads will
    fail in a way that looks like a bug in the stage rather than a bad split.
    """
    jobs = max(1, jobs)
    memory = max(2048, available_memory_mb() // jobs)
    threads = max(1, available_cpus() // jobs)
    return memory, threads


def describe() -> str:
    """One line for the log, so a run records what it thought it had."""
    source = ("PIPELINE_MEMORY_MB" if _int_env("PIPELINE_MEMORY_MB")
              else "SLURM" if _int_env("SLURM_MEM_PER_NODE") or _int_env("SLURM_MEM_PER_CPU")
              else "cgroup" if _cgroup_memory_mb()
              else "system")
    return (f"{available_cpus()} cpus, {available_memory_mb() / 1024:.1f} GiB usable "
            f"(detected via {source}, {RESERVE_FRACTION:.0%} reserved)")


def suggested_jobs() -> int:
    """A starting point for `--jobs`, from the smaller of the two constraints.

    Memory is normally what binds. The per-session stages hold a book for every symbol in the
    session, and eight gigabytes per worker is the figure that has been observed to be enough
    for a full cross-section; below that the book build and the DuckDB aggregations start
    spilling.
    """
    by_memory = max(1, available_memory_mb() // 8192)
    by_cpu = max(1, available_cpus() // 4)
    return max(1, min(by_memory, by_cpu, 8))
