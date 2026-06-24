"""Dump the committed CardCash buy-catalog fixture to a searchable CSV.

Output: build/cardcash_catalog_dump.csv  (gitignored via build/)
Columns: id, name, aliases

Usage:
    uv run python scripts/dump_cardcash_catalog.py
"""

from __future__ import annotations

import csv
from pathlib import Path

from zeal.ingestion.competitor.cardcash import CardCashClient

_FIXTURE = Path("tests/fixtures/cardcash/buy_catalog.html")
_OUTPUT = Path("build/cardcash_catalog_dump.csv")


def main() -> None:
    catalog = CardCashClient.parse_catalog(_FIXTURE.read_text(encoding="utf-8"))
    _OUTPUT.parent.mkdir(exist_ok=True)
    with _OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "aliases"])
        for entry in sorted(catalog.values(), key=lambda e: e["name"]):
            writer.writerow([entry["id"], entry["name"], "|".join(entry.get("aliases") or [])])
    print(f"Wrote {len(catalog)} entries to {_OUTPUT}")


if __name__ == "__main__":
    main()
