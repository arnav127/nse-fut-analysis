"""Move the report's inputs between the machine that computes and the machine that typesets.

A compute node rarely has LaTeX and a laptop cannot hold 250 GB of tick data, so the two
halves of the report are split. The analysis runs wherever the data is and writes the
quantities it computed; this packages those, and the same script unpacks them on a machine
that can typeset.

What goes in is small - a few megabytes - because the document is built from *results*, not
from data. The result tables, the recorded quantities with their units and provenance, and
the universe selection. Nothing here is a parquet file.

    on the cluster:   python scripts/paper_bundle.py export
    on your machine:  python scripts/paper_bundle.py import paper_bundle.tar.gz
                      python run_all.py --stage paper

The figures and generated tables are deliberately *not* included. They are rebuilt on import
from the same result files, so a bundle cannot carry a figure that disagrees with the numbers
beside it.
"""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import RESULTS_DIR  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

logger = setup_logger("Bundle", "stage8_report.log")

DEFAULT_ARCHIVE = PROJECT_ROOT / "paper_bundle.tar.gz"
MANIFEST_NAME = "bundle_manifest.json"

# Everything the typesetting half reads, as (label, path relative to the project root).
# Directories are included recursively but filtered by suffix, so a stray parquet in the
# results directory does not turn a 4 MB bundle into a 400 MB one.
CONTENTS = [
    ("results", Path("data/results"), {".csv", ".json"}),
    ("universe", Path("config/universe_2022.json"), None),
    ("universe detail", Path("config/universe_2022_candidates.csv"), None),
]


def _members() -> List[Path]:
    found: List[Path] = []
    for label, relative, suffixes in CONTENTS:
        path = PROJECT_ROOT / relative
        if path.is_file():
            found.append(path)
        elif path.is_dir():
            found.extend(p for p in sorted(path.rglob("*"))
                         if p.is_file() and (suffixes is None or p.suffix in suffixes))
        else:
            logger.info(f"[BUNDLE] {label} absent ({relative}); skipped")
    return found


def export(archive: Path) -> int:
    members = _members()
    if not members:
        logger.error("[BUNDLE] nothing to export; run the analysis stages first")
        return 1

    metrics = PROJECT_ROOT / "data" / "results" / "metrics.json"
    if not metrics.exists():
        logger.error(f"[BUNDLE] {metrics} is missing. The document is built from the recorded "
                     f"quantities, so run `python run_all.py --stage report` here first - it "
                     f"writes them even when it cannot typeset.")
        return 1

    manifest = {
        "created": datetime.now(timezone.utc).isoformat(),
        "files": len(members),
        "bytes": sum(p.stat().st_size for p in members),
        # Recorded so an import can say what it is unpacking, and so a bundle that turns up
        # a month later can be identified without opening it.
        "source": str(PROJECT_ROOT),
    }
    try:
        manifest["metrics"] = len(json.loads(metrics.read_text(encoding="utf-8"))["metrics"])
    except (OSError, json.JSONDecodeError, KeyError):
        manifest["metrics"] = 0

    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as tar:
        for path in members:
            tar.add(path, arcname=str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
        # Written into the archive rather than beside it, so the two cannot be separated.
        info = tarfile.TarInfo(MANIFEST_NAME)
        payload = json.dumps(manifest, indent=2).encode()
        info.size = len(payload)
        import io

        tar.addfile(info, io.BytesIO(payload))

    logger.info(f"[BUNDLE] {len(members)} files, {manifest['metrics']} recorded quantities "
                f"-> {archive} ({archive.stat().st_size / 1e6:.1f} MB)")
    print(f"\n{archive}\n\nOn a machine with LaTeX:\n"
          f"    python scripts/paper_bundle.py import {archive.name}\n"
          f"    python run_all.py --stage paper")
    return 0


def import_(archive: Path) -> int:
    if not archive.exists():
        logger.error(f"[BUNDLE] {archive} not found")
        return 1

    with tarfile.open(archive, "r:gz") as tar:
        try:
            manifest = json.loads(tar.extractfile(MANIFEST_NAME).read())
            logger.info(f"[BUNDLE] {manifest['files']} files, {manifest['metrics']} recorded "
                        f"quantities, created {manifest['created']} on {manifest['source']}")
        except (KeyError, AttributeError, json.JSONDecodeError):
            logger.warning("[BUNDLE] no manifest; extracting anyway")

        for member in tar.getmembers():
            if member.name == MANIFEST_NAME:
                continue
            # Refuse anything that would land outside the project. A tar can name "../" and
            # ordinary extraction will happily follow it.
            target = (PROJECT_ROOT / member.name).resolve()
            if PROJECT_ROOT.resolve() not in target.parents and target != PROJECT_ROOT.resolve():
                logger.error(f"[BUNDLE] refusing path outside the project: {member.name}")
                return 1
            tar.extract(member, PROJECT_ROOT)

    logger.info(f"[BUNDLE] extracted into {PROJECT_ROOT}")
    print("\nNow build the document:\n    python run_all.py --stage paper")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="action", required=True)

    out = sub.add_parser("export", help="package the report's inputs")
    out.add_argument("archive", nargs="?", type=Path, default=DEFAULT_ARCHIVE)

    inn = sub.add_parser("import", help="unpack a bundle into this checkout")
    inn.add_argument("archive", type=Path)

    args = parser.parse_args()
    return export(args.archive) if args.action == "export" else import_(args.archive)


if __name__ == "__main__":
    raise SystemExit(main())
