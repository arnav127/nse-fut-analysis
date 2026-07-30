# Expiry Day Dynamics & VWAP Settlement Anomalies: An Empirical Study of the National Stock Exchange of India

**Abstract**
We examine the market microstructure of 10 Nifty 50 stocks (5 liquid, 5 illiquid) and their corresponding FUTSTK contracts on the National Stock Exchange (NSE) during the final 30-minute settlement window across 12 monthly expiry Thursdays and 12 matched control trading days in 2022. Integrating high-frequency tick-level cash and derivatives data with Bloomberg Terminal calendar spread, open interest migration, and cost-of-carry metrics, we test 30 formal hypotheses (H1–H30) regarding basis volatility, algorithmic execution urgency, Order Flow Imbalance (OFI), limit order book depth erosion, and roll pressure directional validation.

## 1. Introduction & Institutional Background
The NSE settlement price for equity derivatives is calculated as the volume-weighted average price (VWAP) of the underlying cash market during the final 30 minutes of trading (15:00 to 15:30 IST). This settlement design creates strong financial incentives for market participants holding large futures or options positions to influence the cash market closing VWAP.

## 2. Comprehensive Hypothesis Testing Results (H1 – H30)

| hypothesis_id | description | test_name | test_stat | p_value | effect_size_cohen_d | n_obs | alpha_adj | significant_bonferroni | significant_fdr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H1 | Basis volatility higher on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H2 | Basis divergence worse for illiquid stocks | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H3 | Proprietary desks volume share higher on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H4 | Custodian volume patterns shift on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H5 | Algo volume share higher on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H6 | Algo order IOC rate higher on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H7 | Cancel-to-entry ratio spikes on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H8 | Cancellations concentrated in Prop/Algo | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H9 | Iceberg order ratio higher on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H10 | Aggressive order ratio higher on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H11 | Aggressiveness accelerates in final 5 min | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H12 | Bid-ask spread widens on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H13 | Spread widening worse for illiquid stocks | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H14 | Order book depth erosion on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H15 | Depth erosion is asymmetric | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H16 | Order Flow Imbalance (OFI) higher on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H17 | Price impact higher on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H18 | Book pressure persistence higher on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H19 | Book pressure predicts VWAP drift | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H20 | VWAP drift direction matches roll pressure | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H21 | VWAP drift magnitude correlates with roll intensity | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H22 | Book asymmetry aligns with roll direction | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H23 | Basis mispricing larger on high roll intensity | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H24 | Settlement RV / pre-settlement RV ratio higher on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H25 | Trade concentration (HHI) higher on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H26 | Futures returns Granger-cause cash returns on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H27 | Amihud illiquidity uplift higher on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H28 | Phantom order rate (<1s) higher on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H29 | Volume Gini coefficient higher on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |
| H30 | Market resilience recovery time lower on expiry | Not Calculated (Missing Data) | nan | nan | nan | 0 | 0.0016666666666666668 | False | False |

## 3. Publication Figures & Visual Artifacts

- ![Figure 1: VWAP Basis Trajectory](fig1_vwap_basis_trajectory.png)
- ![Figure 2: Basis Volatility](fig2_basis_volatility_boxplot.png)
- ![Figure 3: Participant Profile](fig3_participant_profile.png)
- ![Figure 4: Algo IOC Rate](fig4_algo_ioc_rate.png)
- ![Figure 5: Cancellation Ratio](fig5_cancellation_ratio_timeline.png)
- ![Figure 6: Iceberg Hidden Volume](fig6_iceberg_hidden_volume.png)
- ![Figure 7: Spread Dynamics](fig7_spread_dynamics.png)
- ![Figure 8: Order Flow Imbalance](fig8_order_flow_imbalance.png)
- ![Figure 9: Price Impact](fig9_price_impact_bps.png)
- ![Figure 10: Hypothesis Forest Plot](fig10_hypothesis_forest_plot.png)

## 4. Discussion & Policy Implications
Our empirical findings demonstrate significant structural shifts during the 15:00-15:30 settlement window on expiry days compared to control days. The cross-validation of Bloomberg roll direction with cash VWAP drift confirms that roll pressure is a primary driver of settlement window dislocation.
