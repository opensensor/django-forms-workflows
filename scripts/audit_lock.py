"""Audit every locked version, including alternate Python-version resolutions."""

import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

with Path("poetry.lock").open("rb") as source:
    packages = tomllib.load(source)["package"]

# pip-audit rejects duplicate names, so audit alternate versions in separate batches.
batches = []
for package in packages:
    name, version = package["name"], package["version"]
    for batch in batches:
        if name not in batch:
            batch[name] = version
            break
    else:
        batches.append({name: version})

failed = False
with tempfile.TemporaryDirectory() as directory:
    for number, batch in enumerate(batches):
        path = Path(directory) / f"requirements-{number}.txt"
        path.write_text(
            "".join(f"{name}=={version}\n" for name, version in batch.items())
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "-r",
                str(path),
                "--no-deps",
                "--disable-pip",
            ],
            check=False,
        )
        failed |= result.returncode != 0
sys.exit(int(failed))
