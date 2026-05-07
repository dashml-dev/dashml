"""
Secrets handling for generated artifacts.

Generated code reads database credentials from environment variables (DASHML_DB_*
for SQL, DASHML_BQ_* for BigQuery), never from baked-in literals. This module
emits the boilerplate code and auxiliary files (.env.example, .gitignore,
SECRETS.md) that make this work.

Convention: env vars use the DASHML_ prefix to avoid collisions with other tools
that may already define DB_HOST / DB_USER in the same shell.
"""
from typing import Any, Dict, Optional


SQL_ENV_VARS = [
    ("DASHML_DB_TYPE", "postgresql, mysql, or sqlite"),
    ("DASHML_DB_HOST", "database host (e.g. localhost or db.example.com)"),
    ("DASHML_DB_PORT", "database port (e.g. 5432 for PostgreSQL, 3306 for MySQL)"),
    ("DASHML_DB_NAME", "database name (or file path for sqlite)"),
    ("DASHML_DB_USER", "database user"),
    ("DASHML_DB_PASSWORD", "database password (the only required secret)"),
]

BQ_ENV_VARS = [
    ("DASHML_BQ_PROJECT", "Google Cloud project ID containing the dataset"),
    ("DASHML_BQ_CREDENTIALS", "path to service account JSON file (optional — falls back to gcloud auth)"),
]


def emit_sql_env_loader() -> str:
    """
    Emit Python boilerplate that constructs DATABASE_URL from environment.

    The generated code:
    - Optionally loads a .env file via python-dotenv (no error if dotenv missing)
    - Reads DASHML_DB_TYPE, _HOST, _PORT, _NAME, _USER, _PASSWORD from env
    - Constructs DATABASE_URL based on DASHML_DB_TYPE
    - Raises a clear error if any required variable is missing
    """
    return '''import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_required = ["DASHML_DB_TYPE", "DASHML_DB_HOST", "DASHML_DB_PORT",
             "DASHML_DB_NAME", "DASHML_DB_USER", "DASHML_DB_PASSWORD"]
_missing = [v for v in _required if not os.environ.get(v)]
if _missing:
    raise RuntimeError(
        "Missing required environment variables: " + ", ".join(_missing) +
        ". See .env.example next to this file."
    )

_DB_TYPE = os.environ["DASHML_DB_TYPE"].lower()
_DB_HOST = os.environ["DASHML_DB_HOST"]
_DB_PORT = os.environ["DASHML_DB_PORT"]
_DB_NAME = os.environ["DASHML_DB_NAME"]
_DB_USER = os.environ["DASHML_DB_USER"]
_DB_PASSWORD = os.environ["DASHML_DB_PASSWORD"]

if _DB_TYPE == "postgresql":
    DATABASE_URL = f"postgresql://{_DB_USER}:{_DB_PASSWORD}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"
elif _DB_TYPE == "mysql":
    DATABASE_URL = f"mysql+pymysql://{_DB_USER}:{_DB_PASSWORD}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"
elif _DB_TYPE == "sqlite":
    DATABASE_URL = f"sqlite:///{_DB_NAME}"
else:
    raise RuntimeError(f"Unsupported DASHML_DB_TYPE: {_DB_TYPE}. Use postgresql, mysql, or sqlite.")
'''


def emit_bq_env_loader(project: str) -> str:
    """
    Emit Python boilerplate that initializes a BigQuery client from environment.

    The generated code:
    - Optionally loads a .env file via python-dotenv
    - Uses DASHML_BQ_PROJECT from env if set, otherwise the build-time project
      (project ID is not a secret — it is a public identifier baked into SQL
      queries; env override allows redirecting client to a different project
      without rebuilding, e.g. for cost attribution)
    - Reads DASHML_BQ_CREDENTIALS (optional, runtime-only) for service account path
    - Builds a bigquery.Client using a service account file if credentials path
      is set, otherwise falls back to default credentials (gcloud auth or
      GOOGLE_APPLICATION_CREDENTIALS)

    Args:
        project: Build-time project ID (required; embedded in SQL queries)
    """
    return f'''import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROJECT_ID = os.environ.get("DASHML_BQ_PROJECT", "{project}")

_BQ_CREDENTIALS = os.environ.get("DASHML_BQ_CREDENTIALS")
if _BQ_CREDENTIALS:
    from google.oauth2 import service_account
    _credentials = service_account.Credentials.from_service_account_file(
        _BQ_CREDENTIALS,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    client = bigquery.Client(credentials=_credentials, project=PROJECT_ID)
else:
    client = bigquery.Client(project=PROJECT_ID)
'''


def emit_env_example(data_type: str, db_config: Optional[Dict[str, Any]]) -> str:
    """
    Generate a .env.example file listing required env variables.

    If db_config is provided (i.e. user passed --db-* flags at build time),
    those values are inlined as visible defaults to make local-machine setup
    a one-step copy: `cp .env.example .env` and the dashboard runs.

    For password fields the value is always blank — the user must fill it in.
    """
    lines = [
        "# DashML — environment configuration for the generated dashboard.",
        "# Copy this file to .env and fill in the values for your environment.",
        "# .env is gitignored; never commit real credentials.",
        "",
    ]

    if data_type == "sql":
        cfg = db_config or {}
        defaults = {
            "DASHML_DB_TYPE": cfg.get("type") or "postgresql",
            "DASHML_DB_HOST": cfg.get("host") or "localhost",
            "DASHML_DB_PORT": str(cfg.get("port") or "5432"),
            "DASHML_DB_NAME": cfg.get("database") or "your_database",
            "DASHML_DB_USER": cfg.get("user") or "your_user",
            "DASHML_DB_PASSWORD": "",
        }
        for var, hint in SQL_ENV_VARS:
            value = defaults.get(var, "")
            lines.append(f"# {hint}")
            lines.append(f"{var}={value}")
            lines.append("")
    elif data_type == "bigquery":
        cfg = db_config or {}
        defaults = {
            "DASHML_BQ_PROJECT": cfg.get("project") or "your-gcp-project",
            "DASHML_BQ_CREDENTIALS": cfg.get("credentials_path") or "",
        }
        for var, hint in BQ_ENV_VARS:
            value = defaults.get(var, "")
            lines.append(f"# {hint}")
            lines.append(f"{var}={value}")
            lines.append("")

    return "\n".join(lines)


def emit_gitignore() -> str:
    """Generate .gitignore for the artifact directory."""
    return ".env\n__pycache__/\n*.pyc\n"


def emit_secrets_readme(data_type: str) -> str:
    """Generate SECRETS.md with operator instructions."""
    if data_type == "sql":
        return """# Database credentials

This dashboard reads database credentials from environment variables at runtime.
No credentials are baked into `app.py` — the same artifact runs on any machine
once the environment is populated.

## Quick start (local development)

1. Copy the template:

       cp .env.example .env

2. Edit `.env` and fill in the values (especially `DASHML_DB_PASSWORD`).

3. Run the dashboard. If `python-dotenv` is installed, `.env` is loaded
   automatically. Otherwise export the variables in your shell first:

       export $(grep -v '^#' .env | xargs)
       python app.py

## Production deployment

Do not ship `.env`. Provide variables through your deployment platform's
secret mechanism:

- Docker: `docker run --env-file .env ...` or `environment:` in `docker-compose.yml`
- Kubernetes: a `Secret` mounted as env vars
- systemd: `EnvironmentFile=` directive in the unit file
- CI/CD: secret variables (GitHub Actions, GitLab CI, etc.)

## Required variables

| Variable               | Required | Description                                 |
|------------------------|----------|---------------------------------------------|
| `DASHML_DB_TYPE`       | yes      | `postgresql`, `mysql`, or `sqlite`          |
| `DASHML_DB_HOST`       | yes      | database host                               |
| `DASHML_DB_PORT`       | yes      | database port                               |
| `DASHML_DB_NAME`       | yes      | database name (or sqlite file path)         |
| `DASHML_DB_USER`       | yes      | database user                               |
| `DASHML_DB_PASSWORD`   | yes      | database password                           |

The `.env` file is listed in `.gitignore`. The `app.py` source file is safe to
commit to a public repository — it contains no secrets.
"""
    elif data_type == "bigquery":
        return """# BigQuery credentials

This dashboard reads BigQuery configuration from environment variables at
runtime. No credentials are baked into `app.py` — the same artifact runs on any
machine once the environment is populated.

## Quick start (local development)

1. Copy the template:

       cp .env.example .env

2. Edit `.env`. Set `DASHML_BQ_PROJECT`. For credentials choose one:
   - leave `DASHML_BQ_CREDENTIALS` blank and authenticate via `gcloud auth application-default login`,
   - or set `DASHML_BQ_CREDENTIALS` to the path of a service account JSON file,
   - or set the standard `GOOGLE_APPLICATION_CREDENTIALS` variable.

3. Run the dashboard:

       python app.py

## Production deployment

Do not ship `.env` or service account JSON files in your image. Mount them at
deploy time:

- Docker: `docker run -v /etc/secrets:/secrets:ro --env-file .env ...`
- Kubernetes: a `Secret` mounted at `/secrets/` and `DASHML_BQ_CREDENTIALS=/secrets/sa.json`
- GCP-hosted (Cloud Run, GKE): use Workload Identity — leave `DASHML_BQ_CREDENTIALS` unset

## Required variables

| Variable                | Required | Description                                              |
|-------------------------|----------|----------------------------------------------------------|
| `DASHML_BQ_PROJECT`     | yes      | Google Cloud project ID                                  |
| `DASHML_BQ_CREDENTIALS` | no       | path to service account JSON; falls back to default auth |

The `.env` file is listed in `.gitignore`. The `app.py` source file is safe to
commit to a public repository — it contains no secrets.
"""
    return ""
