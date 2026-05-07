# BigQuery credentials

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
