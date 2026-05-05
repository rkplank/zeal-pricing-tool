from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from zeal.models.merchant import MerchantConfig
from zeal.models.pricing import CompetitorAggregate, GlobalConstants, PriceRecommendation
from zeal.pricing.engine import compute_prices

BASELINE_FIXTURE = Path("tests/fixtures/spreadsheet_baseline.json")

DEMO_CONSTANTS = GlobalConstants(
    ebay_sale_costs=0.13,
    paypal_sell_costs=0.03,
    ebay_postage_costs=0.01,
    online_store_postage_costs=0.03,
    online_sell_bonus_competitive=0.065,
    online_sell_bonus_zen_nocomp=0.085,
    in_store_bad_debt=0.048,
    in_mail_bad_debt=0.02,
    online_bad_debt=0.05,
)


def seed_demo_data(conn: sqlite3.Connection, fixture_path: Path = BASELINE_FIXTURE) -> int:
    """Seed realistic Phase 2 data from the golden spreadsheet baseline fixture."""

    records = _load_fixture_records(fixture_path)
    _seed_global_constants(conn, DEMO_CONSTANTS)
    _seed_competitor_source(conn)
    for record in records:
        _seed_merchant(conn, MerchantConfig(**record["config"]))

    run_id = conn.execute(
        """
        INSERT INTO refresh_runs (status, completed_at, processed, total)
        VALUES ('completed', datetime('now'), ?, ?)
        RETURNING id
        """,
        (len(records), len(records)),
    ).fetchone()[0]

    for record in records:
        cfg = MerchantConfig(**record["config"])
        result = compute_prices(
            record["ebay_sell_input"],
            "high",
            CompetitorAggregate(),
            cfg,
            DEMO_CONSTANTS,
        )
        _seed_ebay_summary(conn, record, "high")
        _seed_recommendation(conn, run_id, record, cfg, result)

    conn.commit()
    return int(run_id)


def _load_fixture_records(fixture_path: Path) -> list[dict[str, Any]]:
    if not fixture_path.exists():
        raise FileNotFoundError(f"Baseline fixture not found: {fixture_path}")
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Baseline fixture must contain a list: {fixture_path}")
    return data


def _seed_global_constants(conn: sqlite3.Connection, constants: GlobalConstants) -> None:
    descriptions = {
        "ebay_sale_costs": "eBay seller fee",
        "paypal_sell_costs": "PayPal processing fee",
        "ebay_postage_costs": "eBay shipment cost",
        "online_store_postage_costs": "Zeal storefront shipment cost",
        "online_sell_bonus_competitive": "Competitive/T24 storefront markdown component",
        "online_sell_bonus_zen_nocomp": "Zen/NC storefront markdown component",
        "in_store_bad_debt": "In-store expected bad debt",
        "in_mail_bad_debt": "In-mail expected bad debt",
        "online_bad_debt": "Online expected bad debt",
        "competitor_electronic_markdown": "v2 competitor electronic fallback markdown",
    }
    for key, value in constants.model_dump().items():
        conn.execute(
            """
            INSERT INTO global_constants (key, value, description)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                description = excluded.description,
                updated_at = datetime('now')
            """,
            (key, value, descriptions.get(key)),
        )


def _seed_competitor_source(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO competitor_sources (source_name, collection_method, notes)
        VALUES ('cardcash', 'scraper', 'Phase 2 placeholder; no scraper runs yet')
        ON CONFLICT(source_name) DO UPDATE SET
            collection_method = excluded.collection_method,
            notes = excluded.notes,
            updated_at = datetime('now')
        """
    )


def _seed_merchant(conn: sqlite3.Connection, cfg: MerchantConfig) -> None:
    conn.execute(
        """
        INSERT INTO merchants (
            merchant_id, display_name, tier,
            in_store_margin, in_mail_margin, e_bonus, ebay_differential,
            in_store_eligible, in_mail_eligible, electronic_eligible,
            online_sell_override, electronic_buy_override, ebay_weight,
            merch_credit_variant, inclusion_regex, exclusion_regex, notes, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(merchant_id) DO UPDATE SET
            display_name = excluded.display_name,
            tier = excluded.tier,
            in_store_margin = excluded.in_store_margin,
            in_mail_margin = excluded.in_mail_margin,
            e_bonus = excluded.e_bonus,
            ebay_differential = excluded.ebay_differential,
            in_store_eligible = excluded.in_store_eligible,
            in_mail_eligible = excluded.in_mail_eligible,
            electronic_eligible = excluded.electronic_eligible,
            online_sell_override = excluded.online_sell_override,
            electronic_buy_override = excluded.electronic_buy_override,
            ebay_weight = excluded.ebay_weight,
            merch_credit_variant = excluded.merch_credit_variant,
            inclusion_regex = excluded.inclusion_regex,
            exclusion_regex = excluded.exclusion_regex,
            notes = excluded.notes,
            is_active = 1,
            updated_at = datetime('now')
        """,
        (
            cfg.merchant_id,
            cfg.display_name,
            cfg.tier,
            cfg.in_store_margin,
            cfg.in_mail_margin,
            cfg.e_bonus,
            cfg.ebay_differential,
            int(cfg.in_store_eligible),
            int(cfg.in_mail_eligible),
            int(cfg.electronic_eligible),
            cfg.online_sell_override,
            cfg.electronic_buy_override,
            cfg.ebay_weight,
            int(cfg.merch_credit_variant),
            _default_inclusion_regex(cfg.display_name),
            None,
            cfg.notes,
        ),
    )


def _seed_ebay_summary(conn: sqlite3.Connection, record: dict[str, Any], confidence: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO ebay_summary (
            merchant_id, summary_date, ebay_sell_pct,
            sample_size, most_recent_observation, confidence
        ) VALUES (?, date('now'), ?, ?, ?, ?)
        """,
        (
            record["merchant_id"],
            record["ebay_sell_input"],
            10 if record["ebay_sell_input"] is not None else 0,
            None,
            confidence if record["ebay_sell_input"] is not None else "none",
        ),
    )


def _seed_recommendation(
    conn: sqlite3.Connection,
    run_id: int,
    record: dict[str, Any],
    cfg: MerchantConfig,
    result: PriceRecommendation,
) -> None:
    conn.execute(
        """
        INSERT INTO price_recommendations (
            merchant_id, refresh_run_id,
            online_sell, in_mail_buy, in_store_buy, electronic_buy,
            ebay_sell_pct, ebay_confidence, no_data,
            formula_breakdown_json, config_snapshot_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cfg.merchant_id,
            run_id,
            _numeric_or_none(result.online_sell.final_value),
            _numeric_or_none(result.in_mail_buy.final_value),
            _numeric_or_none(result.in_store_buy.final_value),
            _numeric_or_none(result.electronic_buy.final_value),
            record["ebay_sell_input"],
            result.confidence if record["ebay_sell_input"] is not None else "none",
            int(result.no_data),
            json.dumps(
                {
                    "online_sell": [s.model_dump() for s in result.online_sell.breakdown],
                    "in_mail_buy": [s.model_dump() for s in result.in_mail_buy.breakdown],
                    "in_store_buy": [s.model_dump() for s in result.in_store_buy.breakdown],
                    "electronic_buy": [s.model_dump() for s in result.electronic_buy.breakdown],
                },
                sort_keys=True,
            ),
            cfg.model_dump_json(),
        ),
    )


def _numeric_or_none(value: float | str) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _default_inclusion_regex(display_name: str) -> str:
    escaped_words = [word for word in display_name.lower().replace("&", " ").split() if word]
    return ".*".join(escaped_words) or display_name.lower()
