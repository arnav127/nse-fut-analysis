"""
main.py — Master Pipeline Runner for NSE Expiry Day Dynamics & VWAP Settlement Anomalies.

Usage:
  python main.py --stage parse              # Run Stage 1 (parse raw files)
  python main.py --stage enrich             # Run Stage 2 (enrichment)
  python main.py --stage analyze            # Run Stage 3 (trade-level analysis)
  python main.py --stage clob               # Run Stage 4 (CLOB reconstruction)
  python main.py --stage clob-analyze       # Run Stage 5 (CLOB-based analysis)
  python main.py --stage bloomberg          # Run Stage 6 (Bloomberg analysis)
  python main.py --stage report             # Run Stage 7 (generate report & charts)
  python main.py --stage all                # Run entire pipeline end-to-end
"""
import argparse
from stage1_parse.run_parse_all import run_parse
from stage2_enrich.run_enrich_all import run_enrich
from stage3_analysis.run_all_analysis import run_analysis
from stage4_clob.run_clob_all import run_clob
from stage5_clob_analysis.run_clob_analysis import run_clob_analysis
from stage6_bloomberg.run_bloomberg_analysis import run_bloomberg
from stage7_report.generate_report import generate_report

def main():
    parser = argparse.ArgumentParser(description="NSE Expiry Day VWAP Analysis Pipeline")
    parser.add_argument(
        "--stage",
        choices=["parse", "enrich", "analyze", "clob", "clob-analyze", "bloomberg", "report", "all"],
        default="all",
        help="Stage of the pipeline to run"
    )
    parser.add_argument("--date", help="Process a single date in DDMMYYYY format")
    parser.add_argument("--symbol", help="Process a single symbol (for CLOB stage)")
    args = parser.parse_args()

    stg = args.stage

    if stg in ("parse", "all"):
        run_parse(single_date=args.date)

    if stg in ("enrich", "all"):
        run_enrich()

    if stg in ("analyze", "all"):
        run_analysis()

    if stg in ("clob", "all"):
        run_clob(single_date=args.date, single_symbol=args.symbol)

    if stg in ("clob-analyze", "all"):
        run_clob_analysis()

    if stg in ("bloomberg", "all"):
        run_bloomberg()

    if stg in ("report", "all"):
        generate_report()

if __name__ == "__main__":
    main()
