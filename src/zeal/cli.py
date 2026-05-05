import argparse
from pathlib import Path

from zeal.db.connection import DEFAULT_DB_PATH, apply_schema, get_connection
from zeal.db.seed import BASELINE_FIXTURE, seed_demo_data


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


def main() -> None:
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

    serve = subparsers.add_parser("serve", help="Run the local read-only dashboard")
    serve.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        metavar="PATH",
        help="Path to the SQLite database file (default: %(default)s)",
    )
    serve.add_argument("--host", default="127.0.0.1", help="Bind host (default: %(default)s)")
    serve.add_argument("--port", type=int, default=8000, help="Bind port (default: %(default)s)")

    args = parser.parse_args()
    if args.command == "init-db":
        cmd_init_db(args)
    elif args.command in {"seed", "seed-demo"}:
        cmd_seed(args)
    elif args.command == "serve":
        cmd_serve(args)


if __name__ == "__main__":
    main()
