# BigQuery

## Configuration

```yaml
warehouse:
  type: bigquery
  project_id: your_project
  private_key_path: /path/to/key.json  # optional, falls back to default credentials
  database: your_dataset
```

## Authentication

briq uses the Google Cloud client library. Authentication works via:

1. Service account JSON key file (`private_key_path`)
2. Application Default Credentials (ADC) — `gcloud auth application-default login`
3. Environment variable `GOOGLE_APPLICATION_CREDENTIALS`

## Install dependencies

```bash
pip install google-cloud-bigquery
```
