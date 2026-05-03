"""
.github/scripts/merge_submissions.py

Reads every user submission from submissions/*/  and merges them into
master/ CSV files.  Deduplication is case-insensitive and strips a
leading "the " so entries like:

    army painter / Army Painter / The Army Painter / the army painter

all resolve to the same canonical record.

Run from repo root on the living-library branch.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

SUBMISSIONS_DIR = Path("submissions")
MASTER_DIR      = Path("master")

# (filename, headers, dedup_key_fn)
TRACKERS = [
    (
        "paints.csv",
        ["brand", "name", "type", "color"],
        lambda r: (_norm(r.get("brand", "")), _norm(r.get("name", ""))),
    ),
    (
        "materials.csv",
        ["name", "type", "brand", "color"],
        lambda r: (_norm(r.get("name", "")), _norm(r.get("brand", ""))),
    ),
    (
        "tools.csv",
        ["name", "type", "brand"],
        lambda r: (_norm(r.get("name", "")), _norm(r.get("brand", ""))),
    ),
    (
        "models.csv",
        ["name", "game_system", "faction", "type", "scale"],
        lambda r: (
            _norm(r.get("name", "")),
            _norm(r.get("game_system", "")),
            _norm(r.get("faction", "")),
        ),
    ),
]

# ── Normalisation ──────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    """Lower-case, strip leading 'the ', collapse whitespace."""
    s = s.strip().lower()
    s = re.sub(r"^the\s+", "", s)
    s = re.sub(r"\s+", " ", s)
    return s

# ── Merge logic ────────────────────────────────────────────────────────────────

def _read_csv(path: Path, headers: list[str]) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            # Keep only known columns; fill missing ones with empty string
            rows.append({h: row.get(h, "") for h in headers})
        return rows


def _write_csv(path: Path, headers: list[str], rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def merge(filename: str, headers: list[str], key_fn):
    master_path = MASTER_DIR / filename

    # Start with whatever is already in master
    seen:   dict[tuple, dict] = {}
    merged: list[dict]        = []

    for row in _read_csv(master_path, headers):
        k = key_fn(row)
        if k not in seen:
            seen[k] = row
            merged.append(row)

    # Walk every user submission folder
    new_count = 0
    for user_dir in sorted(SUBMISSIONS_DIR.iterdir()):
        if not user_dir.is_dir():
            continue
        sub_file = user_dir / filename
        for row in _read_csv(sub_file, headers):
            k = key_fn(row)
            if not k[0]:          # skip rows with blank primary key
                continue
            if k not in seen:
                seen[k] = row
                merged.append(row)
                new_count += 1

    # Sort alphabetically by the first two header columns for readability
    sort_keys = headers[:2]
    merged.sort(key=lambda r: tuple(_norm(r.get(h, "")) for h in sort_keys))

    _write_csv(master_path, headers, merged)
    print(f"  {filename}: {len(merged)} total entries ({new_count} new)")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Merging community submissions into master files…\n")
    for fname, hdrs, key_fn in TRACKERS:
        merge(fname, hdrs, key_fn)
    print("\nDone.")
