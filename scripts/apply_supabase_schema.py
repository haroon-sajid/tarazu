"""Apply `infra/supabase/*.sql` to the configured project, in order.

The three files are idempotent by design, so this is safe to re-run and safe to
run against a project that is already partly migrated — which is the usual case,
because `schema.sql` tends to get pasted into the dashboard early and the
migrations after it get forgotten.

    python scripts/apply_supabase_schema.py            # apply
    python scripts/apply_supabase_schema.py --check    # report only, change nothing

Needs `SUPABASE_DB_URL` in `.env`: a direct `postgresql://` connection, from
Project Settings -> Database. **Nothing else in Tarazu uses that connection** —
the backend reaches Postgres only through PostgREST with the service-role key.
Schema changes are DDL, and PostgREST does not do DDL.

The alternative, if you would rather not put the database password on this
machine, is to paste each file into the dashboard SQL editor in the order listed
below. This script exists to make that less tedious, not to be the only way.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402

MIGRATIONS_DIR = REPO_ROOT / "infra" / "supabase"

#: In order. Each one assumes the ones before it have run.
MIGRATIONS = (
    ("schema.sql", "base tables and the audit-trail hardening"),
    ("0002-organizations.sql", "organizations, org_id everywhere, tenant-scoped RLS"),
    ("0003-api-keys.sql", "api_keys, with key_hash unreadable to browser roles"),
    ("0004-revoke-truncate.sql", "revoke TRUNCATE, which RLS does not cover"),
    ("0005-audit-id-is-text.sql", "audit_id is text, matching the ids the app mints"),
)

#: What each migration should leave behind, so --check can say where a project is.
#: Keyed by table for most; 0004 grants nothing and creates nothing, so it is
#: detected by the trigger it installs instead.
EXPECTED_TABLES = {
    "schema.sql": ("cases", "documents", "extractions", "review_items", "flags",
                   "benford_results", "audit_trail"),
    "0002-organizations.sql": ("organizations", "organization_members"),
    "0003-api-keys.sql": ("api_keys",),
    "0004-revoke-truncate.sql": (),
    "0005-audit-id-is-text.sql": (),
}

#: Migrations whose effect is a privilege or a trigger rather than a table.
EXPECTED_TRIGGERS = {"0004-revoke-truncate.sql": ("audit_trail_no_truncate",)}

#: Migrations detected by a column's type: (table, column, expected data_type).
EXPECTED_COLUMN_TYPES = {
    "0005-audit-id-is-text.sql": (("audit_trail", "audit_id", "text"),),
}


def connect(db_url: str):
    """Open a connection, preferring psycopg 3 and falling back to psycopg2."""
    try:
        import psycopg

        return psycopg.connect(db_url, autocommit=True)
    except ImportError:
        pass
    try:
        import psycopg2

        connection = psycopg2.connect(db_url)
        connection.autocommit = True
        return connection
    except ImportError:
        print(
            "Neither psycopg nor psycopg2 is installed.\n"
            "  pip install 'psycopg[binary]'\n"
            "Or paste the files into the dashboard SQL editor instead.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def existing_tables(connection) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select table_name from information_schema.tables where table_schema = 'public'"
        )
        return {row[0] for row in cursor.fetchall()}


def existing_triggers(connection) -> set[str]:
    """From `pg_trigger`, not `information_schema.triggers`.

    The information_schema view follows the SQL standard, which has no TRUNCATE
    trigger — so it silently omits `audit_trail_no_truncate`, which is exactly
    the one worth checking for.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "select t.tgname from pg_trigger t "
            "join pg_class c on c.oid = t.tgrelid "
            "join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'public' and not t.tgisinternal"
        )
        return {row[0] for row in cursor.fetchall()}


def column_types(connection) -> dict[tuple[str, str], str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select table_name, column_name, data_type from information_schema.columns "
            "where table_schema = 'public'"
        )
        return {(row[0], row[1]): row[2] for row in cursor.fetchall()}


def report(connection) -> None:
    """Say which migrations have landed, by what each one leaves behind."""
    present = existing_tables(connection)
    triggers = existing_triggers(connection)
    types = column_types(connection)
    print("Schema state:")
    for filename, description in MIGRATIONS:
        missing = [t for t in EXPECTED_TABLES[filename] if t not in present]
        missing += [
            f"trigger {name}"
            for name in EXPECTED_TRIGGERS.get(filename, ())
            if name not in triggers
        ]
        missing += [
            f"{table}.{column} is {types.get((table, column), 'absent')}, want {expected}"
            for table, column, expected in EXPECTED_COLUMN_TYPES.get(filename, ())
            if types.get((table, column)) != expected
        ]
        mark = "applied " if not missing else "MISSING "
        print(f"  [{mark}] {filename:<26} {description}")
        if missing:
            print(f"             not found: {', '.join(missing)}")


def main() -> int:
    settings = get_settings()
    check_only = "--check" in sys.argv

    if not settings.supabase_db_url:
        print("SUPABASE_DB_URL is not set. Add it to .env.", file=sys.stderr)
        return 1
    if "[YOUR-PASSWORD]" in settings.supabase_db_url:
        print(
            "SUPABASE_DB_URL still has the [YOUR-PASSWORD] placeholder in it.\n"
            "Get the password from Project Settings -> Database -> Database password\n"
            f"(https://supabase.com/dashboard/project/{settings.supabase_project_ref}/settings/database)\n"
            "and put it in .env. URL-encode it if it contains @ : / ? # or %.",
            file=sys.stderr,
        )
        return 1

    print(f"Project: {settings.supabase_project_ref}")
    connection = connect(settings.supabase_db_url)
    try:
        report(connection)
        if check_only:
            return 0

        print()
        for filename, description in MIGRATIONS:
            path = MIGRATIONS_DIR / filename
            if not path.is_file():
                print(f"  ! {filename} not found at {path}", file=sys.stderr)
                return 1
            print(f"  applying {filename} ({description}) ...", end=" ", flush=True)
            with connection.cursor() as cursor:
                cursor.execute(path.read_text(encoding="utf-8"))
            print("ok")

        print()
        report(connection)
    finally:
        connection.close()

    print(
        "\nNext:\n"
        "  1. Storage -> New bucket -> tarazu-documents, with 'Public bucket' OFF.\n"
        "  2. Set DEMO_USER_PASSWORD in .env, then: python scripts/seed_demo_user.py\n"
        "  3. python scripts/seed_demo_case.py\n"
        "  4. Run infra/supabase/verify-audit-immutability.sql in the SQL editor."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
