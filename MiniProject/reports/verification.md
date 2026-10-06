# Implementation verification

Environment: Python 3.11.9, dependencies pinned in `requirements.txt` (Streamlit 1.41.1, Plotly 5.24.1, pandas 2.2.3, NumPy 2.1.3). All data and economics below are simulated.

## Automated checks

- **12 tests passed** in the workspace; machine-readable result: [test_results.xml](test_results.xml).
- Generator reproduces all tables with the same seed. `unit_id`, truth, inspector, shift hour, lighting and device assignments match across assisted alternatives. Truth volume equals total lot sizes; added confirmation time changes only FAIL/UNCERTAIN timing.
- Hand-calculated KPI fixtures cover distinct device false alarms and final false rejects, zero denominators, no final PASS, and no defects.
- ROI fixture checks monthly saving, 6-month net/ROI, 24-month curve, negative/zero savings, missing comparison data, zero capital and actual baseline duration.
- Temporary ETL loads are repeatable and never reset the Dashboard snapshot. SQL weekly totals match facts.
- Ten injected bad staging rows (five inspections, five claims) are quarantined with reasons. Current load reconciles `read = loaded + rejected`; a later clean run passes while preserving historical quarantine. See [quarantine_test.csv](quarantine_test.csv) and [run log](quarantine_test_runs.csv).
- AppTest covers all five pages under normal data, no defects, no final PASS and empty selections; tests missing baseline/assisted dates and all three scenario selections.
- SQLite read-only connection rejects writes.
- After the final display adjustment (rounding subscription coverage up to whole units and explicit no-payback labels), the four Dashboard test cases passed again.

## Fresh local checkout

[fresh_checkout.json](fresh_checkout.json) records a **local Git submission snapshot**, committed and cloned into a separate folder with `MiniProject/` under repository root. This is not a checkout from the remote GitHub repository.

- Regenerating the full nine CSV files produces identical SHA-256 hashes.
- Full ETL from that checkout passes validation: 97,717 inspections, 416 claims, 240 lot/scenario mart rows.
- All 12 tests pass again in that checkout.
- AppTest opens all five pages with the full data from the repository root, using `MiniProject/dashboard/app.py`.
- `pip install --dry-run --no-index -r MiniProject/dashboard/requirements.txt` resolves the shared pinned requirements successfully in the installed environment. No fresh remote Cloud environment has been tested.

## Actual browser evidence

Headless Chrome via Playwright captured [five screenshots](screenshots) from the running Streamlit app before the current color and layout update. No browser JavaScript errors or Streamlit exception elements were found. The screenshots include full main content; expanders remain closed by default. All 12 tests also passed on the current dashboard version on 2026-10-07.

## Default results

Full precision and sample counts are in [default_kpis.csv](default_kpis.csv).

| Measure | Manual | Base |
|---|---:|---:|
| Inspected units in this alternative | 23,236 | 24,827 |
| True defects | 732 | 837 |
| Escaped defects | 232 | 114 |
| Final PASS denominator | 22,410 | 23,172 |
| Escape PPM | 10,352.52 | 4,919.73 |
| Final Recall | 68.31% | 86.38% |
| Units returned by customers | 174 | 94 |
| Modelled cost per unit (THB) | 0.423978 | 0.333845 |

All three assisted scenarios share 24,827 physical simulated units; total distinct units across both periods are **48,063**, not 97,717. At baseline volume 7,771.93 units/month, Base net monthly benefit is **−799.50 THB** after subscriptions, so there is no payback. Base requires **16,643 whole units/month** to cover subscription fees alone; this does not repay the 90,000 THB capital investment.
