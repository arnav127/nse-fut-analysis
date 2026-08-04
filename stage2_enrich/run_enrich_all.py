"""Orchestrator for Stage 2 enrichment."""

from stage2_enrich.duckdb_enricher import run_duckdb_enrich_all


def run_enrich() -> None:
    print("\n=== STAGE 2: MICROSTRUCTURE ENRICHMENT ===")
    run_duckdb_enrich_all()
    print("\n[COMPLETE] Stage 2 enrichment finished.")


if __name__ == "__main__":
    run_enrich()
