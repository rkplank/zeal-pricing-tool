import argparse
from pathlib import Path

from zeal.db.connection import DEFAULT_DB_PATH, apply_schema, get_connection


def cmd_init_db(args: argparse.Namespace) -> None:
    db_path: Path = args.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    apply_schema(conn)
    conn.close()
    print(f"Database initialized at {db_path}")


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

    args = parser.parse_args()
    if args.command == "init-db":
        cmd_init_db(args)


if __name__ == "__main__":
    main()
