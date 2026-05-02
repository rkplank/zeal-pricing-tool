"""
Baseline extraction report for GiftCardPricingData_2025.xlsx.

Usage:
  uv run python scripts/extract_baseline.py [WORKBOOK_PATH] [--output FILE]

Exit code: 0 if zero mismatches, 1 if any mismatch.
Bankrupt-broken and section-divider rows are exclusions, not mismatches.

Confidence note: the spreadsheet has no confidence input, so we pass "high"
to compute_prices for all rows.  Confidence affects PriceRecommendation.confidence
but NOT the four numeric outputs, so it does not affect the diff.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import load_workbook

from zeal.models.pricing import GlobalConstants
from zeal.pricing.engine import compute_prices

# scripts/ is not a package; import sibling module directly
sys.path.insert(0, str(Path(__file__).parent))
from spreadsheet_parser import (
    ParsedRow,
    parse_workbook,
    read_global_constants,
)

_DEFAULT_WORKBOOK = Path(
    r"C:\Users\kandt\OneDrive - Umich\Zeal Cards\Pricing\GiftCardPricingData_2025.xlsx"
)

# Tier → expected margin rows for the audit section (recon §3)
_TIER_EXPECTED_MARGIN: dict[str, dict[str, int]] = {
    "T24": {"in_store": 11, "in_mail": 12},
    "C":   {"in_store": 13, "in_mail": 14},
    "Z":   {"in_store": 15, "in_mail": 16},
    "NC":  {"in_store": 17, "in_mail": 18},
}

# InputsandMargins row → human-readable label for the audit
_IM_ROW_LABEL: dict[int, str] = {
    11: "T24-in-store",  12: "T24-in-mail",
    13: "C-in-store",   14: "C-in-mail",
    15: "Z-in-store",   16: "Z-in-mail",
    17: "NC-in-store",  18: "NC-in-mail",
}


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------


def _channel_diff(
    ss_val: float | str | None,
    eng_val: float | str | None,
    is_eligible: bool,
) -> tuple[bool, str]:
    """
    Compare one channel.  Returns (is_match, display_str).
    is_match=True only when values agree within ±0.001 or both sentinels agree.
    """
    if ss_val is None:
        # #VALUE! — should only appear for bankrupt rows (excluded before this point)
        return False, "?ERR"

    if isinstance(ss_val, str) and ss_val == "No":
        # Spreadsheet disabled this channel
        if not is_eligible:
            # Engine should return None (in_mail/in_store) or "No" (electronic)
            if eng_val is None or eng_val == "No":
                return True, '"No"'
        return False, f'MISMATCH(ss="No",eng={eng_val!r})'

    if not isinstance(ss_val, (int, float)):
        return False, f"?SS({ss_val!r})"

    ss_f = float(ss_val)
    if not isinstance(eng_val, (int, float)):
        return False, f"MISMATCH(ss={ss_f:.4f},eng={eng_val!r})"

    diff = abs(float(eng_val) - ss_f)
    if diff <= 0.001:
        return True, f"{diff:.4f}"
    return False, f"!{diff:.4f}"


def _row_status(matches: list[bool]) -> str:
    return "match" if all(matches) else "MISMATCH"


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

_SEP = (
    "----+--------------------------------+------+----------"
    "+---------+---------+---------+---------+--"
)
_HDR = (
    " Row | Slug                           | Tier | Status   "
    "|  OS     |  IM     |  IS     |  EB     | Notes"
)


def _fmt_row(
    row_num: int,
    slug: str,
    tier: str,
    status: str,
    os_d: str,
    im_d: str,
    is_d: str,
    eb_d: str,
    notes: str,
) -> str:
    return (
        f"{row_num:>4} | {slug:<30} | {tier:<4} | {status:<8} "
        f"| {os_d:>7} | {im_d:>7} | {is_d:>7} | {eb_d:>7} | {notes}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract and diff the spreadsheet baseline.")
    parser.add_argument(
        "workbook",
        nargs="?",
        type=Path,
        default=_DEFAULT_WORKBOOK,
        help="Path to GiftCardPricingData_2025.xlsx",
    )
    parser.add_argument("--output", "-o", type=Path, default=None, help="Write report to file")
    args = parser.parse_args()

    workbook_path: Path = args.workbook
    if not workbook_path.exists():
        print(f"ERROR: workbook not found: {workbook_path}", file=sys.stderr)
        return 2

    # Load global constants once
    wb_v = load_workbook(workbook_path, data_only=True)
    constants = read_global_constants(wb_v)

    # Parse all rows (classification summary printed by parse_workbook)
    print(f"Parsing {workbook_path.name} …")
    parsed_rows = parse_workbook(workbook_path)

    lines, mismatch_count = _build_report(workbook_path, constants, parsed_rows)

    report = "\n".join(lines)
    print(report)

    if args.output:
        args.output.write_text(report, encoding="utf-8")
        print(f"\nReport written to {args.output}", file=sys.stderr)

    return 1 if mismatch_count else 0


def _build_report(
    workbook_path: Path,
    constants: GlobalConstants,
    parsed_rows: list[ParsedRow],
) -> tuple[list[str], int]:
    """Return (report_lines, mismatch_count)."""
    lines: list[str] = []
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines += [
        "=== Zeal Spreadsheet Baseline Extraction Report ===",
        f"Workbook : {workbook_path}",
        f"Generated: {ts}",
        "",
        "Note: confidence='high' is passed to compute_prices for all rows.",
        "Confidence affects PriceRecommendation.confidence only, not the four",
        "numeric outputs — it does not affect any diff in this report.",
        "",
    ]

    # Classification summary
    from collections import Counter
    counts: Counter[str] = Counter(r.classification for r in parsed_rows)
    lines += [
        "--- Classification summary ---",
        f"  normal              : {counts['normal']}",
        f"  no_ebay_data_local  : {counts['no_ebay_data_local']}",
        f"  bankrupt_broken     : {counts['bankrupt_broken']}",
        f"  section_divider     : {counts['section_divider']}",
        f"  skip_blank          : {counts['skip_blank']}",
        f"  total               : {len(parsed_rows)}",
        "",
    ]

    # Global constants
    lines += [
        "--- Global constants extracted ---",
        f"  ebay_sale_costs                : {constants.ebay_sale_costs}",
        f"  paypal_sell_costs              : {constants.paypal_sell_costs}",
        f"  ebay_postage_costs             : {constants.ebay_postage_costs}",
        f"  online_store_postage_costs     : {constants.online_store_postage_costs}",
        f"  online_sell_bonus_competitive  : {constants.online_sell_bonus_competitive}",
        f"  online_sell_bonus_zen_nocomp   : {constants.online_sell_bonus_zen_nocomp}",
        f"  in_store_bad_debt              : {constants.in_store_bad_debt}",
        f"  in_mail_bad_debt               : {constants.in_mail_bad_debt}",
        f"  online_bad_debt                : {constants.online_bad_debt}",
        "",
    ]

    # Per-merchant diff table
    lines += ["--- Merchant baseline diffs ---", _HDR, _SEP]

    mismatches: list[ParsedRow] = []
    audit_drifts: list[str] = []

    for parsed in parsed_rows:
        cls = parsed.classification
        slug = parsed.merchant_id or ""
        tier = parsed.tier or "-"

        if cls in ("skip_blank", "section_divider"):
            continue

        if cls == "bankrupt_broken":
            note = next((n for n in parsed.notes if "bankrupt_broken" in n), "bankrupt_broken")
            lines.append(
                _fmt_row(
                    parsed.row_number, slug, tier, "excluded",
                    "-", "-", "-", "-", note,
                )
            )
            continue

        # normal or no_ebay_data_local
        if parsed.config is None or parsed.spreadsheet_outputs is None:
            lines.append(
                _fmt_row(
                    parsed.row_number, slug, tier, "excluded",
                    "-", "-", "-", "-", "no config",
                )
            )
            continue

        cfg = parsed.config
        ss = parsed.spreadsheet_outputs
        ebay_pct = parsed.ebay_sell_input

        # Guard: engine asserts e_bonus is not None when electronic_eligible=True
        # and no override.  If the parser couldn't resolve an e-bonus row from the
        # D formula, substitute electronic_eligible=False so the engine can run and
        # the mismatch is visible in the report.
        extra_note = ""
        if cfg.electronic_eligible and cfg.e_bonus is None and cfg.electronic_buy_override is None:
            cfg = cfg.model_copy(update={"electronic_eligible": False})
            extra_note = "e_bonus_unresolved: electronic_eligible forced False"

        result = compute_prices(ebay_pct, "high", cfg, constants)

        os_ok, os_d = _channel_diff(ss.online_sell, result.online_sell, True)
        im_ok, im_d = _channel_diff(ss.in_mail_buy, result.in_mail_buy, cfg.in_mail_eligible)
        is_ok, is_d = _channel_diff(ss.in_store_buy, result.in_store_buy, cfg.in_store_eligible)
        eb_ok, eb_d = _channel_diff(
            ss.electronic_buy, result.electronic_buy, cfg.electronic_eligible
        )

        all_ok = os_ok and im_ok and is_ok and eb_ok
        status = "match" if all_ok else "MISMATCH"

        note_parts = list(parsed.notes)
        if extra_note:
            note_parts.append(extra_note)
        row_notes = "; ".join(note_parts)
        lines.append(
            _fmt_row(
                parsed.row_number, slug, tier, status,
                os_d, im_d, is_d, eb_d, row_notes,
            )
        )

        if not all_ok:
            mismatches.append(parsed)

        # Tier-vs-margin-row audit
        if tier in _TIER_EXPECTED_MARGIN and cls in ("normal", "no_ebay_data_local"):
            expected = _TIER_EXPECTED_MARGIN[tier]
            drift_parts: list[str] = []

            is_refs = [int(r[1:]) for r in parsed.formula_refs.get("in_store_buy", [])]
            actual_is = next((n for n in is_refs if n in {11, 13, 15, 17}), None)
            if actual_is is not None and actual_is != expected["in_store"]:
                exp_lbl = _IM_ROW_LABEL.get(expected["in_store"], f"B{expected['in_store']}")
                act_lbl = _IM_ROW_LABEL.get(actual_is, f"B{actual_is}")
                drift_parts.append(f"in_store expects {exp_lbl} but uses {act_lbl}")

            im_refs = [int(r[1:]) for r in parsed.formula_refs.get("in_mail_buy", [])]
            actual_im = next((n for n in im_refs if n in {12, 14, 16, 18}), None)
            if actual_im is not None and actual_im != expected["in_mail"]:
                exp_lbl = _IM_ROW_LABEL.get(expected["in_mail"], f"B{expected['in_mail']}")
                act_lbl = _IM_ROW_LABEL.get(actual_im, f"B{actual_im}")
                drift_parts.append(f"in_mail expects {exp_lbl} but uses {act_lbl}")

            if drift_parts:
                audit_drifts.append(
                    f"  row {parsed.row_number:>3} {slug:<30} tier={tier}: {'; '.join(drift_parts)}"
                )

    lines.append("")

    # Mismatch detail
    lines += ["--- Mismatches ---"]
    if not mismatches:
        lines.append("  (none)")
    else:
        for parsed in mismatches:
            cfg = parsed.config
            ss = parsed.spreadsheet_outputs
            assert cfg is not None and ss is not None
            needs_guard = (
                cfg.electronic_eligible
                and cfg.e_bonus is None
                and cfg.electronic_buy_override is None
            )
            if needs_guard:
                cfg = cfg.model_copy(update={"electronic_eligible": False})
            result = compute_prices(parsed.ebay_sell_input, "high", cfg, constants)
            lines += [
                "",
                f"Row {parsed.row_number} — {parsed.merchant_id}",
                f"  Tier          : {parsed.tier}",
                f"  eBay input    : {parsed.ebay_sell_input}",
                f"  online_sell_override    : {cfg.online_sell_override}",
                f"  electronic_buy_override : {cfg.electronic_buy_override}",
                "  Config:",
                f"    in_store_margin  = {cfg.in_store_margin}",
                f"    in_mail_margin   = {cfg.in_mail_margin}",
                f"    ebay_differential= {cfg.ebay_differential}",
                f"    e_bonus          = {cfg.e_bonus}",
                f"    in_store_eligible= {cfg.in_store_eligible}",
                f"    in_mail_eligible = {cfg.in_mail_eligible}",
                f"    electronic_eligible = {cfg.electronic_eligible}",
                "  Formula refs:",
                f"    online_sell  : {parsed.formula_refs.get('online_sell')}",
                f"    in_mail_buy  : {parsed.formula_refs.get('in_mail_buy')}",
                f"    in_store_buy : {parsed.formula_refs.get('in_store_buy')}",
                f"    electronic   : {parsed.formula_refs.get('electronic_buy')}",
                "  Spreadsheet outputs:",
                f"    online_sell  = {ss.online_sell}",
                f"    in_mail_buy  = {ss.in_mail_buy}",
                f"    in_store_buy = {ss.in_store_buy}",
                f"    electronic   = {ss.electronic_buy}",
                "  Engine outputs:",
                f"    online_sell  = {result.online_sell}",
                f"    in_mail_buy  = {result.in_mail_buy}",
                f"    in_store_buy = {result.in_store_buy}",
                f"    electronic   = {result.electronic_buy}",
            ]
    lines.append("")

    # Tier-vs-margin audit
    lines += ["--- Tier-vs-margin-row audit ---"]
    if not audit_drifts:
        lines.append("  (no drift detected)")
    else:
        lines += audit_drifts
    lines.append("")

    return lines, len(mismatches)


if __name__ == "__main__":
    sys.exit(main())
