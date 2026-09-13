# Expiry Day Dynamics & VWAP Settlement Anomalies: An Empirical Study of the National Stock Exchange of India

**Abstract**
We examine the market microstructure of 10 NSE equities (5 liquid, 5 illiquid) and their FUTSTK contracts during the final 30-minute settlement window, across 12 monthly expiry Thursdays and 12 matched control sessions in 2022. Drawing on high-frequency tick-level NSE cash and derivatives order and trade data, we specify 30 hypotheses (H1-H30) on basis volatility, algorithmic execution urgency, order flow imbalance, limit order book depth erosion and roll pressure. 23 were evaluated on the data available to this run, of which 11 were rejected at a 5 per cent false discovery rate.

## 1. Introduction & Institutional Background
The NSE settlement price for equity derivatives is calculated as the volume-weighted average price (VWAP) of the underlying cash market during the final 30 minutes of trading (15:00 to 15:30 IST). This settlement design creates strong financial incentives for market participants holding large futures or options positions to influence the cash market closing VWAP.

## 2. Comprehensive Hypothesis Testing Results (H1 – H30)

| hypothesis_id | description | test_name | test_stat | p_value | wilcoxon_p_value | effect_size_cohen_d | n_pairs | n_months | mean_expiry | mean_control | note | n_tested | alpha_bonferroni | significant_bonferroni | significant_fdr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H1 | Basis volatility higher on expiry | Not tested (input missing or empty) | nan | nan | nan | nan | 0 | 0 | nan | nan | a2_basis_divergence.csv:basis_std_dev | 23 | 0.002173913043478261 | False | False |
| H2 | Basis divergence worse for illiquid stocks | Not tested (input missing or empty) | nan | nan | nan | nan | 0 | 0 | nan | nan | a2_basis_divergence.csv:basis_range | 23 | 0.002173913043478261 | False | False |
| H3 | Proprietary desk volume share higher on expiry | Paired t-test | 4.483345706242959 | 1.7028281627431286e-05 | 1.2337089695119283e-06 | 0.40927159606719976 | 120 | 12 | 10334471.616666667 | 8240011.8 |  | 23 | 0.002173913043478261 | True | True |
| H4 | Custodian trade counts shift on expiry | Paired t-test | 3.189595995334662 | 0.001821451853815811 | 0.000150153981104204 | 0.2911689459954894 | 120 | 12 | 296654.3333333333 | 258154.38333333333 |  | 23 | 0.002173913043478261 | True | True |
| H5 | Algo volume share higher on expiry | Paired t-test | -1.7414367775051678 | 0.08419125706442089 | 0.9624019312642655 | -0.15897070091811424 | 120 | 12 | 154263174.38333333 | 177018765.41666666 |  | 23 | 0.002173913043478261 | False | False |
| H6 | Algo order IOC rate higher on expiry | Paired t-test | -0.36306054388537395 | 0.717203756532626 | 0.6925113801538751 | -0.03314274160435227 | 120 | 12 | 0.059850733638964884 | 0.06153999176697079 |  | 23 | 0.002173913043478261 | False | False |
| H7 | Cancel-to-entry ratio spikes on expiry | Paired t-test | -3.4203546365322857 | 0.0008574948049130382 | 0.00034360201919019336 | -0.3122342315160194 | 120 | 12 | 0.48202649401061987 | 0.5171207937134545 |  | 23 | 0.002173913043478261 | True | True |
| H8 | Cancellations concentrated in prop/algo flow | Paired t-test | 7.360249535152576 | 2.5910411605252965e-11 | 3.920912992129098e-12 | 0.6718957832116631 | 120 | 12 | 41954.4 | 29798.158333333333 |  | 23 | 0.002173913043478261 | True | True |
| H9 | Iceberg order ratio higher on expiry | Paired t-test | 3.1578798945728015 | 0.002014303478935282 | 0.003619337734265652 | 0.2882736753582599 | 120 | 12 | 0.18765472531192529 | 0.17339750619448474 |  | 23 | 0.002173913043478261 | True | True |
| H10 | Aggressive order ratio higher on expiry | Paired t-test | 0.6122003417184587 | 0.5415732188584804 | 0.779309495349765 | 0.05588598947859514 | 120 | 12 | 0.09272034796822039 | 0.09085827950210783 |  | 23 | 0.002173913043478261 | False | False |
| H11 | Aggressiveness accelerates in the final 5 minutes | Paired t-test | -0.8850682107645206 | 0.37790472017904986 | 0.4491378342837149 | -0.08079530399441076 | 120 | 12 | 0.052245293428551755 | 0.055560299088108896 |  | 23 | 0.002173913043478261 | False | False |
| H12 | Bid-ask spread widens on expiry | Paired t-test | 4.5751416660949396 | 1.175827460327524e-05 | 5.880428438611448e-06 | 0.4176513823836612 | 120 | 12 | 1.4505566636951925 | 1.2274742504442373 |  | 23 | 0.002173913043478261 | True | True |
| H13 | Spread widening worse for illiquid stocks | Paired t-test | 1.2712953864450454 | 0.20610285778167722 | 0.19757767512673208 | 0.1160528600680331 | 120 | 12 | 12.508123147550503 | 11.4075664090146 |  | 23 | 0.002173913043478261 | False | False |
| H14 | Order book depth erosion on expiry | Paired t-test | -0.9135357477877528 | 0.36280802992729666 | 0.8958200385032111 | -0.08339402269178374 | 120 | 12 | 5844.0162175925925 | 6262.103712962964 |  | 23 | 0.002173913043478261 | False | False |
| H15 | Depth erosion is asymmetric | Paired t-test | -2.02197405329248 | 0.04542176590116797 | 0.04890837335508485 | -0.1845801332797407 | 120 | 12 | 0.1464112306986215 | 0.17670629654910427 |  | 23 | 0.002173913043478261 | False | False |
| H16 | Order flow imbalance higher on expiry | Paired t-test | -0.329274700079165 | 0.7425268961079092 | 0.5609783497708847 | -0.030058530141517797 | 120 | 12 | 0.2034905086399446 | 0.2107691883835453 |  | 23 | 0.002173913043478261 | False | False |
| H17 | Price impact higher on expiry | Paired t-test | 2.3526757644877194 | 0.02028016822877426 | 0.027707849358079864 | 0.21476893111760592 | 120 | 12 | 0.005317012739555782 | 0.0 |  | 23 | 0.002173913043478261 | False | True |
| H18 | Book pressure persistence higher on expiry | Paired t-test | -3.283219780527921 | 0.0013477417316760435 | 0.0036040896414889236 | -0.2997155891737171 | 120 | 12 | 0.6460324074074073 | 0.6924722222222222 |  | 23 | 0.002173913043478261 | True | True |
| H19 | Book pressure magnitude higher on expiry | Paired t-test | 1.1446868010510884 | 0.2546360347436781 | 0.23035610613238322 | 0.10449513036901822 | 120 | 12 | 0.04393331888014107 | -0.023104976460274266 |  | 23 | 0.002173913043478261 | False | False |
| H20 | VWAP drift direction matches roll pressure | Not tested (input missing or empty) | nan | nan | nan | nan | 0 | 0 | nan | nan | c3_directional_validation.csv:match_vwap | 23 | 0.002173913043478261 | False | False |
| H21 | VWAP drift magnitude tracks roll intensity | Not tested (input missing or empty) | nan | nan | nan | nan | 0 | 0 | nan | nan | c3_directional_validation.csv:roll_intensity | 23 | 0.002173913043478261 | False | False |
| H22 | Book asymmetry aligns with roll direction | Not tested (input missing or empty) | nan | nan | nan | nan | 0 | 0 | nan | nan | c3_directional_validation.csv:match_book | 23 | 0.002173913043478261 | False | False |
| H23 | Basis mispricing larger on high roll intensity | Not tested (input missing or empty) | nan | nan | nan | nan | 0 | 0 | nan | nan | c2_cost_of_carry.csv:mispricing_bps | 23 | 0.002173913043478261 | False | False |
| H24 | Settlement realised variance rate higher on expiry | Paired t-test | 2.5484982739912585 | 0.012091497848204149 | 1.1375553093630522e-05 | 0.23264499873799888 | 120 | 12 | 2.400296172046063 | 1.440513141538691 |  | 23 | 0.002173913043478261 | False | True |
| H25 | Trade concentration (HHI) higher on expiry | Paired t-test | -0.3422455238327824 | 0.7327698480804059 | 0.17742769460051366 | -0.031242598934731143 | 120 | 12 | 0.04030039897034401 | 0.04051694667201046 |  | 23 | 0.002173913043478261 | False | False |
| H26 | Futures returns Granger-cause cash returns on expiry | Not tested (input missing or empty) | nan | nan | nan | nan | 0 | 0 | nan | nan | a10_lead_lag.csv:granger_f_stat | 23 | 0.002173913043478261 | False | False |
| H27 | Amihud illiquidity uplift higher on expiry | Paired t-test | 1.9864680194540103 | 0.049279451127851814 | 0.04771869574053651 | 0.18133889066959544 | 120 | 12 | -0.6804918284844272 | -0.7201983779167251 |  | 23 | 0.002173913043478261 | False | False |
| H28 | Phantom order rate (<1s) higher on expiry | Paired t-test | 3.9349903969630637 | 0.0001404567150956826 | 0.00015254783079854614 | 0.35921383399714624 | 120 | 12 | 0.349301510268203 | 0.31264476511525335 |  | 23 | 0.002173913043478261 | True | True |
| H29 | Settlement volume Gini higher on expiry | Paired t-test | -1.111877256082203 | 0.26843219418939185 | 0.1799655933918337 | -0.1015000423888618 | 120 | 12 | 0.22312539223131825 | 0.23109324521726288 |  | 23 | 0.002173913043478261 | False | False |
| H30 | Post-shock recovery time differs on expiry | Paired t-test | -4.95261803902753 | 2.444358544782335e-06 | 3.862930360777781e-08 | -0.4521101031137299 | 120 | 12 | 4.479890290992847 | 5.986014299979636 |  | 23 | 0.002173913043478261 | True | True |

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

## 4. Results

Of the 30 hypotheses specified, 23 could be evaluated from the data available to this run, and 11 were rejected at a Benjamini-Hochberg false discovery rate of 5 per cent.

The hypotheses rejected were: H3, H4, H7, H8, H9, H12, H17, H18, H24, H28, H30. Effect sizes and per-test p-values are given in the table above.

The following were not evaluated because their inputs were absent or empty, and no claim is made about them: H1, H2, H20, H21, H22, H23, H26.

