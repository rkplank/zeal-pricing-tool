"""Apply an operator-reviewed CardCash → Zeal merchant mapping to the DB.

The apply path is intentionally separate from the seed path:
- match_cardcash_ids.py produces a PROPOSAL CSV (not committed, not applied).
- The operator reviews and edits the CSV, renames it to the approved path.
- apply_cardcash_mapping() applies the approved CSV to merchants.cardcash_id.
"""

from __future__ import annotations

import csv
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

_LEGAL_SUFFIXES = frozenset({"inc", "llc", "corp", "ltd", "lp", "plc"})


def normalize_merchant_name(name: str) -> str:
    """Normalize a merchant display name for fuzzy matching.

    Steps: NFD decompose → ASCII (drops ®/™), lowercase, replace
    non-alphanumeric with spaces, strip leading 'the', strip trailing
    legal suffixes (inc/llc/corp/ltd/lp/plc), collapse whitespace.
    """
    name = unicodedata.normalize("NFD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    words = name.split()
    if words and words[0] == "the":
        words = words[1:]
    while words and words[-1] in _LEGAL_SUFFIXES:
        words = words[:-1]
    return " ".join(words)


@dataclass(frozen=True)
class MappingResult:
    updated: int
    skipped: int
    conflicted: int
    conflict_details: list[tuple[str, int, int]] = field(default_factory=list)


def apply_cardcash_mapping(
    conn: sqlite3.Connection,
    mapping_path: Path,
    *,
    force: bool = False,
) -> MappingResult:
    """Apply an operator-approved CardCash mapping CSV to merchants.cardcash_id.

    Reads mapping_path (CSV with at minimum columns zeal_merchant_id and
    proposed_cardcash_id).  Skips rows with an empty proposed_cardcash_id.
    Refuses to overwrite a non-NULL cardcash_id unless force=True — reports
    conflicts instead.  Runs all updates in a single transaction and commits.
    Does NOT touch any table other than merchants.cardcash_id.
    """
    rows = _read_mapping_csv(mapping_path)

    updated = 0
    skipped = 0
    conflicted = 0
    conflict_details: list[tuple[str, int, int]] = []

    for row in rows:
        merchant_id = row["zeal_merchant_id"].strip()
        proposed_raw = row.get("proposed_cardcash_id", "").strip()

        if not proposed_raw:
            skipped += 1
            continue

        proposed_id = int(proposed_raw)

        current = conn.execute(
            "SELECT cardcash_id FROM merchants WHERE merchant_id = ?",
            (merchant_id,),
        ).fetchone()

        if current is None:
            skipped += 1
            continue

        existing = current["cardcash_id"]

        if existing is not None and not force:
            conflict_details.append((merchant_id, int(existing), proposed_id))
            conflicted += 1
            continue

        conn.execute(
            "UPDATE merchants SET cardcash_id = ?, updated_at = datetime('now') "
            "WHERE merchant_id = ?",
            (proposed_id, merchant_id),
        )
        updated += 1

    conn.commit()

    return MappingResult(
        updated=updated,
        skipped=skipped,
        conflicted=conflicted,
        conflict_details=conflict_details,
    )


def _read_mapping_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)
