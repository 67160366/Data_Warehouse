"""Package only the deliverable project, excluding environments and test sandboxes."""
from pathlib import Path
import hashlib
import json
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = [".streamlit", "config", "dashboard", "data", "docs", "src", "tests", "scripts", "reports"]
FILES = [".gitignore", "README.md", "PLAN_3Eyes_DW_Dashboard.md", "requirements.txt", "requirements-dev.txt", "run.py", "run.ps1", "run.sh"]


def main():
    destination = ROOT / "reports/threeeyes_submission.zip"
    paths = [ROOT / file for file in FILES]
    for folder in DIRECTORIES:
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                     and p.suffix not in (".zip", ".pyc") and p.name != "submission_manifest.json")
    with ZipFile(destination, "w", ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(paths):
            archive.write(path, "MiniProject/" + path.relative_to(ROOT).as_posix())
    manifest = {"archive": destination.name, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "files": len(paths), "size_bytes": destination.stat().st_size}
    (ROOT / "reports/submission_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
