"""Orchestrator for Stage 6 Bloomberg-integrated analysis modules (C1-C4)."""

import time

from stage6_bloomberg.c1_roll_pressure import run_c1_roll_pressure
from stage6_bloomberg.c2_cost_of_carry import run_c2_cost_of_carry
from stage6_bloomberg.c3_directional_validation import run_c3_directional_validation
from stage6_bloomberg.c4_basis_event_study import run_c4_basis_event_study


def run_bloomberg() -> None:
    print("\n=== STAGE 6: BLOOMBERG INTEGRATED ANALYSIS (C1-C4) ===")
    t_start = time.time()

    modules = [
        ("C1: Roll Pressure", run_c1_roll_pressure),
        ("C2: Cost of Carry", run_c2_cost_of_carry),
        ("C3: Directional Validation", run_c3_directional_validation),
        ("C4: Basis Event Study", run_c4_basis_event_study),
    ]

    for name, func in modules:
        t0 = time.time()
        func()
        print(f"[TIMING] Module {name} finished in {time.time() - t0:.2f}s")

    print(f"\n[COMPLETE] Stage 6 Bloomberg analysis finished in {time.time() - t_start:.2f}s")


if __name__ == "__main__":
    run_bloomberg()
