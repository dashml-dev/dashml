# Database credentials

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
