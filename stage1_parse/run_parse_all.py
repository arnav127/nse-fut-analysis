"""
run_parse_all.py — Orchestrate Stage 1 parsing across dates.
"""
from config.settings import ALL_TARGET_DATES
from stage1_parse.parse_cash_orders import parse_cash_orders
from stage1_parse.parse_cash_trades import parse_cash_trades
from stage1_parse.parse_fao_orders import parse_fao_orders
from stage1_parse.parse_fao_trades import parse_fao_trades
from utils.spark_session import get_spark

def run_parse(single_date=None):
    """
    Run parsing for all dates or a single specified date.
    """
    dates_to_process = [single_date] if single_date else ALL_TARGET_DATES
    spark = get_spark("NSE_Stage1_Parsing")

    for d in dates_to_process:
        print(f"\n=== Processing Date: {d} ===")
        parse_cash_orders(d, spark=spark)
        parse_cash_trades(d, spark=spark)
        parse_fao_orders(d, spark=spark)
        parse_fao_trades(d, spark=spark)

    print("\n[COMPLETE] Stage 1 parsing process finished.")

if __name__ == "__main__":
    run_parse()
