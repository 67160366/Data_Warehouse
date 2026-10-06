# Data Quality Report

Validation status: **PASS**
Fact load run: 3; current rejected rows: 0.
Clean data checks run only when the current fact load has no rejects. Historical quarantine is retained.

| Check | Actual | Expected | Status |
|---|---|---|---|
| Foreign key violations | 0 | 0 | PASS |
| SQLite integrity | ok | ok | PASS |
| Catch + escape = true defects | 0 | 0 | PASS |
| One date and shift per lot | 0 | 0 | PASS |
| Consistent paired truth and factors | 0 | 0 | PASS |
| No inflated lot counts | 0 | 0 | PASS |
| fact_inspection: staging = loaded + rejected | 97717 = 97717 + 0 | equal | PASS |
| fact_customer_claim: staging = loaded + rejected | 416 = 416 + 0 | equal | PASS |
| Run log reconciliation | 0 | 0 | PASS |
| Clean data: complete lot/scenario counts | 0 | 0 | PASS |
| Clean data: all assisted units have three scenarios | 0 | 0 | PASS |

Inspection rows: 97,717; distinct physical simulated units: 48,063.
Assisted scenario rows must not be summed as production volume.
