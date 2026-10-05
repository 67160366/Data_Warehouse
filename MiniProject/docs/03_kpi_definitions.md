# KPI Definitions

| KPI | Definition |
|---|---|
| K1 Escape PPM | Escaped defective units ÷ units with final PASS × 1,000,000 |
| K2 Final detection recall | Defective units with final FAIL ÷ all defective units |
| K3 Recall by defect | K2 grouped by defect name |
| K4 Human miss rate | Defective manual units with final PASS ÷ defective manual units, grouped by hour/shift |
| K5 False alarm rate | Good units with final FAIL ÷ all good units |
| K6 Device uncertain rate | Assisted units with device UNCERTAIN ÷ assisted units |
| K7 Override rate | Override rows ÷ device FAIL recommendations |
| K8 Inspection time / throughput | Mean inspect seconds; throughput = 3600 ÷ mean seconds |
| K9 Defect rate by lot/customer | Ground-truth defective units ÷ units in lot. For assisted, scenario 2 is used for one representative count. |
| K10 Cost of quality | Claim + rework + labor cost |
| K11 Cost saving | Difference in per-unit K10 × comparable volume, less ongoing device subscription where projected |
| K12 ROI / payback | Net cumulative savings after device cost ÷ device cost; payback = upfront device cost ÷ positive monthly net savings |

K1, K2, K5–K8 are also available from `vw_kpi_weekly`; defect recall, miss rate, and lot rates are available from their corresponding SQL views. Dashboard derives aggregate ratios from filtered facts to preserve correct denominator behavior. Cost inputs are in `config/assumptions.csv` and are all labeled as assumptions unless cited otherwise.
