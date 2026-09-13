# Bloomberg Terminal Data Export Instructions

Export the following 4 CSV files into `data/bloomberg/`:

1. `calendar_spreads.csv`
   - Columns: `date`, `symbol`, `near_month_price`, `far_month_price`, `calendar_spread`
2. `open_interest.csv`
   - Columns: `date`, `symbol`, `near_month_oi`, `far_month_oi`, `total_oi`, `near_month_oi_pct`
3. `cost_of_carry.csv`
   - Columns: `date`, `symbol`, `spot_close`, `near_futures_close`, `actual_basis`, `days_to_expiry`, `annualized_coc_pct`
4. `futures_volume.csv`
   - Columns: `date`, `symbol`, `near_month_volume`, `far_month_volume`, `volume_ratio`
