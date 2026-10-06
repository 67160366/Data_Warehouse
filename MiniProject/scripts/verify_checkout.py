"""Create a local submission Git checkout and verify it without workspace imports."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ["config", "dashboard", "data", "docs", "src", "tests", "scripts", "reports"]
FILES = [".gitignore", "README.md", "PLAN_3Eyes_DW_Dashboard.md", "requirements.txt", "requirements-dev.txt", "run.py", "run.ps1", "run.sh"]


def run(args, cwd):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


def main():
    base = ROOT / ".verification"
    base.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="release-", dir=base))
    source = work / "source"
    project = source / "MiniProject"
    project.mkdir(parents=True)
    for directory in DIRECTORIES:
        shutil.copytree(ROOT / directory, project / directory,
                        ignore=shutil.ignore_patterns("__pycache__", "*.zip", ".gitkeep"))
    for file in FILES:
        shutil.copy2(ROOT / file, project / file)
    run(["git", "init", "--initial-branch=main"], source)
    run(["git", "add", "MiniProject"], source)
    run(["git", "-c", "user.name=Local verification", "-c", "user.email=verification@example.invalid",
         "-c", "commit.gpgsign=false", "commit", "-m", "Local submission verification snapshot"], source)
    checkout = work / "checkout"
    run(["git", "clone", "--no-local", str(source), str(checkout)], work)
    copied = checkout / "MiniProject"
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (copied / "data/raw").glob("*.csv")}
    run([sys.executable, "run.py", "data"], copied)
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (copied / "data/raw").glob("*.csv")}
    assert before == after, "Full generator does not reproduce delivered CSVs"
    run([sys.executable, "run.py", "etl", "--reset"], copied)
    tests = run([sys.executable, "-m", "pytest", "tests", "-q", "--basetemp", str(work / "tests")], copied)
    smoke = """from streamlit.testing.v1 import AppTest
at = AppTest.from_file('MiniProject/dashboard/app.py', default_timeout=60).run()
assert not at.exception
for page in at.sidebar.radio[0].options:
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception
print('5 full-data pages passed from repository root')
"""
    smoke_result = run([sys.executable, "-c", smoke], checkout)
    # Avoid connecting to any package index: verify relative requirements resolution locally.
    dependencies = run([sys.executable, "-m", "pip", "install", "--dry-run", "--no-index", "-r",
                        "MiniProject/dashboard/requirements.txt"], checkout)
    evidence = {"status": "PASS", "checkout": str(checkout), "source": "local submission Git snapshot, not remote GitHub",
                "python": sys.version, "csv_reproducible": before == after, "tests": tests,
                "repository_root_app_test": smoke_result, "relative_dependencies": "PASS",
                "snapshot_rows": json.loads((copied / "reports/data_manifest.json").read_text())["rows"]}
    (ROOT / "reports/fresh_checkout.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
