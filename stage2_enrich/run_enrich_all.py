"""
run_enrich_all.py — Orchestrator for Stage 2 enrichment using zero-JVM DuckDB C++.
"""
from stage2_enrich.duckdb_enricher import run_duckdb_enrich_all

def run_enrich(engine="duckdb"):
    print(f"\n=== STAGE 2: ENRICHMENT (Engine: {engine.upper()}) ===")
    run_duckdb_enrich_all()
    print("\n[COMPLETE] Stage 2 enrichment finished.")

if __name__ == "__main__":
    run_enrich(engine="duckdb")
