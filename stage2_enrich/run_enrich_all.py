"""
run_enrich_all.py — Orchestrator for Stage 2 enrichment.
"""
from stage2_enrich.enrich_cash import enrich_cash_orders, enrich_cash_trades
from stage2_enrich.enrich_fao import enrich_fao_orders, enrich_fao_trades
from utils.spark_session import get_spark

def run_enrich():
    spark = get_spark("NSE_Stage2_Enrichment")
    print("\n=== STAGE 2: ENRICHMENT ===")
    enrich_cash_orders(spark=spark)
    enrich_cash_trades(spark=spark)
    enrich_fao_orders(spark=spark)
    enrich_fao_trades(spark=spark)
    print("\n[COMPLETE] Stage 2 enrichment finished.")

if __name__ == "__main__":
    run_enrich()
