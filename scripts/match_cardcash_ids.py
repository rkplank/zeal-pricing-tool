"""Generate a CardCash merchant-match proposal CSV for operator review.

Loads the buy catalog from the committed fixture (no live network) and the
Zeal merchant list from the baseline fixture, computes normalized name /
alias similarity scores for every pair, and writes a ranked proposal to
build/cardcash_match_proposal.csv (gitignored via build/).

The operator reviews the CSV, removes incorrect candidates, fills in any
'none'-tier rows manually, and renames/copies the result to
data/cardcash_mapping_approved.csv before running the apply path.

Usage:
    uv run python scripts/match_cardcash_ids.py
"""

from __future__ import annotations

import csv
import difflib
import json
from pathlib import Path
from typing import Any

from zeal.db.competitor_mapping import normalize_merchant_name
from zeal.ingestion.competitor.cardcash import CardCashClient

_FIXTURE_CATALOG = Path("tests/fixtures/cardcash/buy_catalog.html")
_FIXTURE_BASELINE = Path("tests/fixtures/spreadsheet_baseline.json")
_OUTPUT_DIR = Path("build")
_OUTPUT_CSV = _OUTPUT_DIR / "cardcash_match_proposal.csv"

_HIGH_THRESHOLD = 0.92
_REVIEW_THRESHOLD = 0.80
_TOP_K = 3

_CSV_FIELDS = [
    "zeal_merchant_id",
    "zeal_display_name",
    "proposed_cardcash_id",
    "cardcash_name",
    "score",
    "match_tier",
]


def _score_tier(score: float) -> str:
    if score >= 1.0:
        return "exact"
    if score >= _HIGH_THRESHOLD:
        return "high"
    if score >= _REVIEW_THRESHOLD:
        return "review"
    return "none"


def _best_score(normalized_zeal: str, cc_normalized_names: list[str]) -> float:
    best = 0.0
    for cc_norm in cc_normalized_names:
        if not cc_norm or not normalized_zeal:
            continue
        if cc_norm == normalized_zeal:
            return 1.0
        score = difflib.SequenceMatcher(None, normalized_zeal, cc_norm).ratio()
        if score > best:
            best = score
    return best


def main() -> None:
    catalog = CardCashClient.parse_catalog(_FIXTURE_CATALOG.read_text(encoding="utf-8"))

    # Pre-compute normalized names for every CardCash entry once.
    cc_entries: list[tuple[int, str, list[str]]] = []
    for entry in catalog.values():
        raw_name: str = entry["name"]
        aliases: list[str] = entry.get("aliases") or []
        normalized = [normalize_merchant_name(n) for n in [raw_name] + aliases]
        cc_entries.append((int(entry["id"]), raw_name, normalized))

    baseline_data: list[dict[str, Any]] = json.loads(
        _FIXTURE_BASELINE.read_text(encoding="utf-8")
    )
    zeal_merchants = [(rec["merchant_id"], rec["config"]["display_name"]) for rec in baseline_data]

    _OUTPUT_DIR.mkdir(exist_ok=True)

    tier_counts: dict[str, int] = {"exact": 0, "high": 0, "review": 0, "none": 0}
    output_rows: list[dict[str, str]] = []

    for zeal_id, zeal_name in zeal_merchants:
        normalized_zeal = normalize_merchant_name(zeal_name)

        scored: list[tuple[float, int, str]] = [
            (_best_score(normalized_zeal, cc_norms), cc_id, cc_raw)
            for cc_id, cc_raw, cc_norms in cc_entries
        ]
        scored.sort(key=lambda x: -x[0])
        top = scored[:_TOP_K]

        best_score_val = top[0][0] if top else 0.0
        best_tier = _score_tier(best_score_val)
        tier_counts[best_tier] += 1

        if best_tier == "none":
            # No usable candidate — leave blank so apply skips it.
            output_rows.append(
                {
                    "zeal_merchant_id": zeal_id,
                    "zeal_display_name": zeal_name,
                    "proposed_cardcash_id": "",
                    "cardcash_name": "",
                    "score": "",
                    "match_tier": "none",
                }
            )
        else:
            # Emit top candidate, plus additional candidates in the review band.
            for rank, (score, cc_id, cc_raw) in enumerate(top):
                if rank > 0 and score < _REVIEW_THRESHOLD:
                    break
                output_rows.append(
                    {
                        "zeal_merchant_id": zeal_id,
                        "zeal_display_name": zeal_name,
                        "proposed_cardcash_id": str(cc_id),
                        "cardcash_name": cc_raw,
                        "score": f"{score:.4f}",
                        "match_tier": _score_tier(score),
                    }
                )

    with _OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(output_rows)

    no_candidate = tier_counts["none"]
    print(f"Match proposal written to: {_OUTPUT_CSV}")
    print(f"  Zeal merchants : {len(zeal_merchants)}")
    print(f"  exact          : {tier_counts['exact']}")
    print(f"  high  (>=0.92) : {tier_counts['high']}")
    print(f"  review(>=0.80) : {tier_counts['review']}")
    print(f"  none  (< 0.80) : {no_candidate}")
    print(
        f"\nOperator action: review {_OUTPUT_CSV}, correct/remove rows, rename to "
        "data/cardcash_mapping_approved.csv, then run apply_cardcash_mapping()."
    )


if __name__ == "__main__":
    main()
