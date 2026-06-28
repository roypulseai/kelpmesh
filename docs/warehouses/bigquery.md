# BigQuery

## Configuration

```yaml
warehouse:
  type: bigquery
  project_id: my-gcp-project
  database: my_dataset          # BigQuery dataset name
  private_key_path: /path/to/service-account.json   # optional; uses ADC if omitted
  threads: 8
```

## Install dependencies

```bash
pip install google-cloud-bigquery
```

## Authentication

KelpMesh uses the Google Cloud client library. Authentication sources (tried in order):

1. `private_key_path` — service account JSON key file
2. `GOOGLE_APPLICATION_CREDENTIALS` environment variable
3. Application Default Credentials (`gcloud auth application-default login`)
4. Workload Identity (when running on GKE or Cloud Run)

For local development:

```bash
gcloud auth application-default login
```

## IAM permissions

| Role | Purpose |
|---|---|
| `roles/bigquery.dataEditor` | Create/drop tables and views |
| `roles/bigquery.jobUser` | Run queries |
| `roles/bigquery.metadataViewer` | Read table schemas |

```bash
gcloud projects add-iam-policy-binding my-gcp-project \
  --member="serviceAccount:KelpMesh@my-gcp-project.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"
```

## Materialization support

| Materialization | Supported | Notes |
|---|---|---|
| `view` | ✅ | `CREATE OR REPLACE VIEW` |
| `table` | ✅ | `CREATE TABLE AS SELECT` |
| `incremental` (append) | ✅ | `INSERT INTO` |
| `incremental` (merge) | ✅ | BigQuery `MERGE` statement |
| `ephemeral` | ✅ | Inlined as CTE |

### Incremental merge example

```sql
-- {{ config(materialized="incremental", unique_key="customer_id", incremental_strategy="merge") }}
SELECT
  customer_id,
  email,
  plan,
  updated_at
FROM `raw.customers`
WHERE updated_at >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
```

KelpMesh generates a BigQuery MERGE statement:

```sql
MERGE `my_dataset`.`dim_customers` AS target
USING (...) AS source
ON target.`customer_id` = source.`customer_id`
WHEN MATCHED THEN UPDATE SET target.`email` = source.`email`, ...
WHEN NOT MATCHED THEN INSERT (`customer_id`, `email`, ...) VALUES (source.`customer_id`, ...)
```

## Cost controls

- Set a `maximum_bytes_billed` query limit in your project to cap accidental full-table scans.
- Prefer incremental models over full table refreshes on datasets > 10 GB.
- Use `--dry-run` with the BigQuery API before scheduling expensive models.
