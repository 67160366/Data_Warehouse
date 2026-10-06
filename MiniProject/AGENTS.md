# Project guide for Codex

## Start a session

Read `docs/SESSION_NOTES.md`, `README.md`, and the documentation relevant to the task. This is the existing 3Eyes factory quality and investment dashboard, built with Python 3.11, Streamlit, Plotly, and SQLite. Continue this application unless the user requests a platform change.

## Run and verify

From this folder in PowerShell:

```powershell
.\.venv\Scripts\python.exe run.py app
.\.venv\Scripts\python.exe -m pytest tests -q
```

Use the existing virtual environment when available. For a fresh machine, follow README setup. Tests create temporary databases. `python run.py all` regenerates data and resets the warehouse; use it only when rebuilding data is part of the task. The dashboard normally reads the existing snapshot.

## Files to know

- `dashboard/app.py`: five pages, filters, charts, and display logic.
- `dashboard/style.py`: CSS, banner, chart palette, and system colors.
- `.streamlit/config.toml`: Streamlit light theme and widget colors.
- `dashboard/data.py`: cached, read-only SQLite access and selection.
- `src/metrics.py`: shared KPI and investment calculations.
- `docs/03_kpi_definitions.md`: metric definitions and denominators.
- `docs/02_storyboard.md`: purpose of each dashboard page.
- `PLAN_3Eyes_DW_Dashboard.md`: original implementation plan.
- `reports/verification.md`: earlier verification evidence, not current deployment status.

## Maintain the project

Preserve Thai text and UTF-8 encoding. Keep the simulated-data disclaimer visible. Keep zero-denominator and empty-filter behavior, sample counts, separate baseline/assisted periods, and distinct assisted scenarios. Do not change economics or KPI definitions for a visual redesign. Manual is indigo; 3Eyes is teal; escaped-defect risk is rose. Use distinct category colors and explicit Plotly colors with `theme=None`.

After dashboard changes, run existing dashboard tests and inspect actual browser screenshots where possible. `scripts/capture_dashboard.py` captures five pages from a running local server; Chrome can be passed with `--executable`. Record changes, verification, and remaining work in `docs/SESSION_NOTES.md` so a new session can continue. Do not treat old submission ZIPs or screenshots as current evidence without regenerating them.

Keep searches scoped: exclude `.venv`, `.uv-cache`, `.verification`, `.pytest_cache`, and `__pycache__`. No Power BI report project currently exists; `config/powerbi_theme.json` is an optional theme, not a report.
