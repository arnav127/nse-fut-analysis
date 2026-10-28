"""Link every F&O file on the library's shares into one folder, choosing a complete copy.

The derivatives files for 2022 are spread over four read-only shares (mounted at /mnt/nse,
/mnt/nse_e, /mnt/nse_f and /mnt/nse_g), in download folders of varying names, and some files
exist more than once. Each file has a .trg record with its size in bytes; where copies differ,
the one whose size matches is linked. Files with no complete copy are linked anyway and
listed, since a part that is incomplete loses only the securities in it.

Writes nothing to the shares. Usage: python scripts/fao_links.py [--out DIR]
"""

from __future__ import annotations

import argparse
import collections
import glob
import os
import re
from pathlib import Path

ROOTS = ["/mnt/nse", "/mnt/nse_e", "/mnt/nse_f", "/mnt/nse_g"]
NAME = re.compile(r"FAO_(Orders|Trades)_(\d{8})_(\d+)\.DAT\.gz$")


def recorded_size(path: str):
    trg = path + ".trg"
    if not os.path.exists(trg):
        return None
    match = re.search(r"(\d+) size in bytes", open(trg, errors="replace").read())
    return int(match.group(1)) if match else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path.home() / "sandbox/data/raw/fao_all"))
    out = Path(ap.parse_args().out)
    best = {}
    for root in ROOTS:
        for path in glob.glob(f"{root}/**/FAO_*_*.DAT.gz", recursive=True):
            name = os.path.basename(path)
            if not NAME.match(name):
                continue
            expected = recorded_size(path)
            complete = expected is None or expected == os.stat(path).st_size
            if name not in best or (complete and not best[name][1]):
                best[name] = (path, complete)
    out.mkdir(parents=True, exist_ok=True)
    for name, (path, _) in best.items():
        link = out / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(path)
    sessions = collections.defaultdict(set)
    for name in best:
        kind, date, _ = NAME.match(name).groups()
        sessions[(kind, date[4:] + date[2:4])].add(date)
    for key in sorted(sessions):
        print(key, len(sessions[key]), "sessions")
    incomplete = sorted(n for n, (_, ok) in best.items() if not ok)
    print(f"{len(best)} files linked in {out}; no complete copy of: {incomplete}")


if __name__ == "__main__":
    main()
