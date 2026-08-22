"""Application configuration, read from the environment.

Variable names are listed in `.env.example`. Nothing is hardcoded here except
safe defaults, and no value is ever logged.

The one decision worth understanding: **`SUPABASE_URL` selects the backing
store.** Set it and the app talks to Supabase (Postgres, Storage, Auth); leave
it unset and the app runs entirely locally on SQLite and the filesystem. The
local mode exists so the pipeline can be run and demoed before the Supabase
project is provisioned — the code path either side of the store is identical.

`.env` in the repo root is loaded once, on import, **without overriding
anything already in the environment**. A real environment variable therefore
always beats the file, which is what makes `SUPABASE_URL= uvicorn ...` and a
container's injected secrets work as expected. Set `TARAZU_DOTENV=0` to skip the
file entirely — the test suite does, so that what `pytest` proves never depends
on whether the developer running it happens to have a `.env`.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

__all__ = [
    "DEFAULT_ORG_ID",
    "DEFAULT_ORG_NAME",
    "Settings",
    "get_settings",
    "reset_settings_cache",
]

logger = logging.getLogger(__name__)

#: backend/app/core/config.py -> core -> app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

#: Where `.env` lives. Overridable so a deployment can point at a mounted file.
ENV_FILE = Path(os.getenv("TARAZU_ENV_FILE") or REPO_ROOT / ".env")

#: The organization every pre-tenancy row is backfilled into, and the one the
#: seeded demo auditor belongs to. The same literal appears in
#: `infra/supabase/0002-organizations.sql`; change one and change the other.
DEFAULT_ORG_ID = "00000000-0000-4000-8000-0000000000d0"
DEFAULT_ORG_NAME = "Tarazu Demo Firm"

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in _TRUE


def _project_ref(url: str | None) -> str | None:
    """`https://abcd.supabase.co` -> `abcd`. The id the Supabase CLI wants."""
    if not url:
        return None
    host = url.split("://", 1)[-1].split("/", 1)[0]
    return host.split(".", 1)[0] or None


def _parse_env_file(text: str) -> dict[str, str]:
    """A minimal `KEY=value` reader, so `.env` works without python-dotenv.

    Handles what `.env.example` actually contains: comments, blank lines,
    `export ` prefixes, and values wrapped in quotes. Anything more exotic
    (multi-line values, interpolation) is python-dotenv's job, and it is used in
    preference to this whenever it is installed.
    """
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_env_file(path: Path | None = None) -> bool:
    """Load `.env` into the environment, never overriding what is already set.

    Returns True if a file was read. Secrets are not logged — only the path and
    the number of names found, which is the most a startup line should say.
    """
    if (os.getenv("TARAZU_DOTENV") or "").strip().lower() in _FALSE:
        return False

    target = path or ENV_FILE
    if not target.is_file():
        return False

    try:
        from dotenv import dotenv_values  # noqa: PLC0415 - optional dependency

        values = {key: value for key, value in dotenv_values(target).items() if value is not None}
    except ImportError:
        values = _parse_env_file(target.read_text(encoding="utf-8"))

    added = [key for key in values if key not in os.environ]
    for key in added:
        os.environ[key] = values[key]
    logger.info("Loaded %s (%d new variables)", target, len(added))
    return True


# Read the file before any `get_settings()` call can observe the environment.
load_env_file()


@dataclass(frozen=True)
class Settings:
    # -- Supabase ----------------------------------------------------------- #
    supabase_url: str | None
    supabase_anon_key: str | None
    supabase_service_role_key: str | None
    supabase_jwt_secret: str | None
    storage_bucket: str
    #: The project ref (the subdomain of `supabase_url`). Derived when unset.
    supabase_project_ref: str | None
    #: The modern browser-safe key, `sb_publishable_...`. Interchangeable with
    #: `supabase_anon_key` wherever an `apikey` header is sent; kept separate so
    #: the frontend can be handed one without reaching for the other.
    supabase_publishable_key: str | None
    #: A direct `postgresql://` connection. **Nothing in the request path uses
    #: this** — the backend reaches Postgres only through PostgREST, with the
    #: service-role key. It exists for schema work, and is read by
    #: `scripts/apply_supabase_schema.py` alone.
    supabase_db_url: str | None

    # -- Local fallback ----------------------------------------------------- #
    local_database_path: Path
    local_storage_path: Path

    # -- Auth --------------------------------------------------------------- #
    demo_user_email: str
    demo_user_password: str | None
    #: Accept requests with no JWT as the demo user. Development only.
    allow_dev_user: bool
    dev_user_id: str
    #: Signs the tokens `POST /v1/auth/login` issues in local (SQLite) mode.
    #: Unused when Supabase is configured — there, tokens come from GoTrue and
    #: are verified with `supabase_jwt_secret`.
    local_jwt_secret: str
    local_token_ttl_seconds: int

    # -- Tenancy ------------------------------------------------------------ #
    #: The organization the seeded demo auditor belongs to, and the one existing
    #: rows are backfilled into by the tenancy migration.
    default_org_id: str
    default_org_name: str

    # -- App ---------------------------------------------------------------- #
    allowed_origins: tuple[str, ...]
    demo_mode: bool

    @property
    def uses_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def rest_url(self) -> str:
        return f"{(self.supabase_url or '').rstrip('/')}/rest/v1"

    @property
    def auth_url(self) -> str:
        return f"{(self.supabase_url or '').rstrip('/')}/auth/v1"

    @property
    def storage_url(self) -> str:
        return f"{(self.supabase_url or '').rstrip('/')}/storage/v1"

    @property
    def jwks_url(self) -> str:
        """Where the project publishes the public keys that sign its tokens.

        Used when a project signs asymmetrically (ES256 and friends), which is
        the modern Supabase default. Legacy HS256 projects never reach it.
        """
        return f"{self.auth_url}/.well-known/jwks.json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    origins = os.getenv("BACKEND_ALLOWED_ORIGINS")
    return Settings(
        supabase_url=os.getenv("SUPABASE_URL") or None,
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY") or None,
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or None,
        supabase_jwt_secret=os.getenv("SUPABASE_JWT_SECRET") or None,
        storage_bucket=os.getenv("SUPABASE_STORAGE_BUCKET") or "tarazu-documents",
        supabase_project_ref=(
            os.getenv("SUPABASE_PROJECT_REF")
            or _project_ref(os.getenv("SUPABASE_URL"))
        ),
        supabase_publishable_key=os.getenv("SUPABASE_PUBLISHABLE_KEY") or None,
        supabase_db_url=os.getenv("SUPABASE_DB_URL") or None,
        local_database_path=Path(
            os.getenv("LOCAL_DATABASE_PATH") or REPO_ROOT / ".local" / "tarazu.db"
        ),
        local_storage_path=Path(
            os.getenv("LOCAL_STORAGE_PATH") or REPO_ROOT / ".local" / "documents"
        ),
        demo_user_email=os.getenv("DEMO_USER_EMAIL") or "auditor@tarazu.local",
        demo_user_password=os.getenv("DEMO_USER_PASSWORD") or None,
        allow_dev_user=_flag("AUTH_ALLOW_DEV_USER"),
        dev_user_id=os.getenv("AUTH_DEV_USER_ID") or "00000000-0000-4000-8000-000000000001",
        local_jwt_secret=(
            os.getenv("LOCAL_JWT_SECRET")
            or "tarazu-local-development-secret-not-for-deployment"
        ),
        local_token_ttl_seconds=int(os.getenv("LOCAL_TOKEN_TTL_SECONDS") or 3600),
        default_org_id=os.getenv("DEFAULT_ORG_ID") or DEFAULT_ORG_ID,
        default_org_name=os.getenv("DEFAULT_ORG_NAME") or DEFAULT_ORG_NAME,
        allowed_origins=tuple(
            origin.strip()
            for origin in (origins or "http://localhost:3000,http://127.0.0.1:3000").split(",")
            if origin.strip()
        ),
        demo_mode=_flag("DEMO_MODE"),
    )


def reset_settings_cache() -> None:
    """Drop the cached settings. For tests that change the environment."""
    get_settings.cache_clear()
