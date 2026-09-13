"""Stage 2 orchestrator."""

from stage2_enrich.enricher import run_enrich

__all__ = ["run_enrich"]

if __name__ == "__main__":
    run_enrich()
