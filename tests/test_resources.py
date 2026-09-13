"""Tests for the budget split.

This is the piece whose failure mode is an out-of-memory kill several hours into a run, so
the arithmetic is pinned rather than trusted. The specific defect it guards: both nsetick and
DuckDB size themselves from the machine, so N concurrent workers each taking a fraction of
the whole is N times the intended footprint.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils import resources  # noqa: E402


@pytest.fixture
def allocation(monkeypatch):
    """A 32-core, 64 GiB allocation declared through the operator override."""
    monkeypatch.setenv("PIPELINE_CPUS", "32")
    monkeypatch.setenv("PIPELINE_MEMORY_MB", str(64 * 1024))
    return 32, 64 * 1024


class TestOverrides:
    def test_explicit_values_win(self, allocation):
        cpus, memory = allocation
        assert resources.available_cpus() == cpus
        assert resources.available_memory_mb() == memory

    def test_slurm_allocation_is_preferred_over_the_node(self, monkeypatch):
        monkeypatch.delenv("PIPELINE_MEMORY_MB", raising=False)
        monkeypatch.delenv("PIPELINE_CPUS", raising=False)
        monkeypatch.setenv("SLURM_CPUS_PER_TASK", "16")
        monkeypatch.setenv("SLURM_MEM_PER_NODE", "32768")
        assert resources.available_cpus() == 16
        # The reserve keeps headroom for the page cache and the parent process.
        assert resources.available_memory_mb() == int(32768 * (1 - resources.RESERVE_FRACTION))

    def test_memory_per_cpu_is_multiplied_out(self, monkeypatch):
        monkeypatch.delenv("PIPELINE_MEMORY_MB", raising=False)
        monkeypatch.setenv("PIPELINE_CPUS", "8")
        monkeypatch.delenv("SLURM_MEM_PER_NODE", raising=False)
        monkeypatch.setenv("SLURM_MEM_PER_CPU", "4096")
        assert resources.available_memory_mb() == int(8 * 4096 * (1 - resources.RESERVE_FRACTION))


class TestWorkerBudget:
    def test_the_split_never_exceeds_the_allocation(self, allocation):
        _, memory = allocation
        for jobs in (1, 2, 3, 4, 8, 16):
            per_worker, threads = resources.worker_budget(jobs)
            assert per_worker * jobs <= memory, jobs
            assert threads * jobs <= 32, jobs

    def test_four_workers_get_a_quarter_each(self, allocation):
        per_worker, threads = resources.worker_budget(4)
        assert per_worker == 16 * 1024
        assert threads == 8

    def test_zero_and_negative_job_counts_are_treated_as_one(self, allocation):
        assert resources.worker_budget(0) == resources.worker_budget(1)
        assert resources.worker_budget(-3) == resources.worker_budget(1)

    def test_a_worker_is_never_given_an_unusable_share(self, allocation):
        # Dividing a small allocation many ways would otherwise hand a worker a few hundred
        # megabytes, which fails inside the stage and looks like a bug in the stage.
        per_worker, threads = resources.worker_budget(1000)
        assert per_worker >= 2048
        assert threads >= 1


class TestSuggestedJobs:
    def test_memory_binds_before_cores_on_this_allocation(self, allocation):
        # 64 GiB at 8 GiB per worker is 8; 32 cores at 4 each is also 8.
        assert resources.suggested_jobs() == 8

    def test_a_small_memory_allocation_caps_the_suggestion(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_CPUS", "64")
        monkeypatch.setenv("PIPELINE_MEMORY_MB", str(16 * 1024))
        assert resources.suggested_jobs() == 2

    def test_never_suggests_fewer_than_one(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_CPUS", "1")
        monkeypatch.setenv("PIPELINE_MEMORY_MB", "2048")
        assert resources.suggested_jobs() == 1


class TestSessionPlanIsPicklable:
    """A plan crosses a process boundary, so it has to survive pickling."""

    def test_round_trip(self):
        import pickle

        from run_all import SessionPlan

        plan = SessionPlan(session="27012022", stages=("parse",), parse_symbols=["RELIANCE"],
                           enrich_symbols=None, book_symbols=None, categories=("cash_trades",),
                           force=False, memory_mb=16384, threads=8)
        assert pickle.loads(pickle.dumps(plan)) == plan
