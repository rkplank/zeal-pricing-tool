from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv

from zeal.config import ZealConfig
from zeal.db.connection import DEFAULT_DB_PATH, apply_schema, get_connection
from zeal.db.seed import BASELINE_FIXTURE, seed_demo_data
from zeal.ingestion.ebay_client_factory import create_ebay_client
from zeal.ingestion.ebay_errors import EbayClientError
from zeal.models.merchant import MerchantRecord
from zeal.pricing.listing_filter import filter_listings


def cmd_init_db(args: argparse.Namespace) -> None:
    db_path: Path = args.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    apply_schema(conn)
    conn.close()
    print(f"Database initialized at {db_path}")


def cmd_seed(args: argparse.Namespace) -> None:
    db_path: Path = args.db_path
    fixture_path: Path = args.fixture_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    apply_schema(conn)
    run_id = seed_demo_data(conn, fixture_path)
    conn.close()
    print(f"Seeded demo data into {db_path} with refresh_run_id={run_id}")


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from zeal.web.app import create_app

    app = create_app(args.db_path)
    uvicorn.run(app, host=args.host, port=args.port)


def cmd_smoke_ebay(args: argparse.Namespace) -> None:
    load_dotenv()
    raise SystemExit(asyncio.run(_run_smoke_ebay(args.merchant, args.limit)))


async def _run_smoke_ebay(merchant_id: str, limit: int) -> int:
    fetch_limit = max(1, limit)
    try:
        config = ZealConfig.from_env()
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 1

    if config.ebay_mode == "synthetic":
        print("Warning: ZEAL_EBAY_MODE=synthetic; using synthetic eBay client.")

    merchant = _load_merchant(config.db_path, merchant_id)
    if merchant is None:
        print(f"Merchant not found: {merchant_id}")
        return 1

    http_client = httpx.AsyncClient()
    try:
        client = create_ebay_client(
            config=config,
            http_client=http_client,
            max_results_default=fetch_limit,
        )
        listings = await client.sold_listings_for_merchant(
            merchant_id=merchant.merchant_id,
            inclusion_regex=merchant.inclusion_regex,
            exclusion_regex=merchant.exclusion_regex,
        )
    except EbayClientError as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 1
    finally:
        await http_client.aclose()

    filtered = filter_listings(listings, merchant)
    histogram = Counter(item.exclusion_reason for item in filtered.excluded)

    print(f"Merchant: {merchant.display_name} ({merchant.merchant_id})")
    print(f"Inclusion regex: {merchant.inclusion_regex}")
    print(f"Raw listings returned: {len(listings)}")
    print("First listings:")
    for listing in listings[: min(3, fetch_limit)]:
        print(
            "- "
            f"{listing.listing_id} | {listing.title} | "
            f"sale_price={listing.sale_price} | face_value={listing.face_value} | "
            f"sold_at={listing.sold_at}"
        )
    print(f"Valid listings: {len(filtered.valid)}")
    print(f"Excluded listings: {len(filtered.excluded)}")
    print("Exclusion reasons:")
    if histogram:
        for reason, count in sorted(histogram.items()):
            print(f"- {reason}: {count}")
    else:
        print("- none: 0")
    return 0


def _load_merchant(db_path: Path, merchant_id: str) -> MerchantRecord | None:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT *
            FROM merchants
            WHERE merchant_id = ? AND is_active = 1
            """,
            (merchant_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    return MerchantRecord(
        merchant_id=str(row["merchant_id"]),
        display_name=str(row["display_name"]),
        tier=row["tier"],
        in_store_margin=float(row["in_store_margin"]),
        in_mail_margin=float(row["in_mail_margin"]),
        ebay_differential=float(row["ebay_differential"]),
        in_store_eligible=bool(row["in_store_eligible"]),
        in_mail_eligible=bool(row["in_mail_eligible"]),
        electronic_eligible=bool(row["electronic_eligible"]),
        merch_credit_variant=bool(row["merch_credit_variant"]),
        e_bonus=float(row["e_bonus"]) if row["e_bonus"] is not None else None,
        online_sell_override=(
            float(row["online_sell_override"]) if row["online_sell_override"] is not None else None
        ),
        electronic_buy_override=(
            float(row["electronic_buy_override"])
            if row["electronic_buy_override"] is not None
            else None
        ),
        ebay_weight=float(row["ebay_weight"]),
        notes=str(row["notes"]) if row["notes"] is not None else None,
        inclusion_regex=str(row["inclusion_regex"]),
        exclusion_regex=str(row["exclusion_regex"]) if row["exclusion_regex"] is not None else None,
        is_active=bool(row["is_active"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def main() -> None:
    import truststore

    truststore.inject_into_ssl()

    parser = argparse.ArgumentParser(description="Zeal pricing tool CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Initialize the database schema")
    init_db.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        metavar="PATH",
        help="Path to the SQLite database file (default: %(default)s)",
    )

    seed = subparsers.add_parser("seed", help="Seed realistic synthetic Phase 2 data")
    seed.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        metavar="PATH",
        help="Path to the SQLite database file (default: %(default)s)",
    )
    seed.add_argument(
        "--fixture-path",
        type=Path,
        default=BASELINE_FIXTURE,
        metavar="PATH",
        help="Path to spreadsheet_baseline.json (default: %(default)s)",
    )

    seed_demo = subparsers.add_parser("seed-demo", help="Alias for seed")
    seed_demo.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        metavar="PATH",
        help="Path to the SQLite database file (default: %(default)s)",
    )
    seed_demo.add_argument(
        "--fixture-path",
        type=Path,
        default=BASELINE_FIXTURE,
        metavar="PATH",
        help="Path to spreadsheet_baseline.json (default: %(default)s)",
    )

    serve = subparsers.add_parser("serve", help="Run the local dashboard")
    serve.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        metavar="PATH",
        help="Path to the SQLite database file (default: %(default)s)",
    )
    serve.add_argument("--host", default="127.0.0.1", help="Bind host (default: %(default)s)")
    serve.add_argument("--port", type=int, default=8000, help="Bind port (default: %(default)s)")

    smoke_ebay = subparsers.add_parser("smoke-ebay", help="Smoke-test configured eBay data")
    smoke_ebay.add_argument("--merchant", required=True, metavar="MERCHANT_ID")
    smoke_ebay.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Display limit (default: %(default)s)",
    )

    args = parser.parse_args()
    if args.command == "init-db":
        cmd_init_db(args)
    elif args.command in {"seed", "seed-demo"}:
        cmd_seed(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "smoke-ebay":
        cmd_smoke_ebay(args)


if __name__ == "__main__":
    main()
