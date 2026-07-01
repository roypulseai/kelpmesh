# KelpMesh Studio

KelpMesh Studio is the optional web UI layer built on top of KelpMesh Core. Core is always free and fully functional from the CLI; Studio adds visual interfaces for lineage, scheduling, and team collaboration.

## Install

```bash
pip install kelpmesh-studio
```

## Start the UI

```bash
# Start with auto-detected project in current directory
kelpmesh-studio

# Specify project directory
kelpmesh-studio --project-dir /path/to/project

# Custom port
kelpmesh-studio --port 8765

# Bind to all interfaces (for remote access)
kelpmesh-studio --host 0.0.0.0 --port 8765
```

Open your browser at `http://localhost:8501`.

## Features

### DAG View
A live, interactive visualization of your entire project DAG:
- Nodes are color-coded by materialization type (view/table/incremental/snapshot)
- Click any node to see: model SQL, description, column list, test results
- Filter by tag, materialization, or search by name
- "Run this model" button triggers `kelpmesh run <model>` and shows progress

### Model Browser
Browse all models in a searchable table:
- Columns: Name, Materialization, Tags, Last Run, Row Count, Status
- Click any row to open the model detail view
- Sort and filter by any column

### Run History
A timeline of all model runs:
- Per-model success/failure status
- Row counts, elapsed time, run ID
- Filter by date range, model, or status
- Export to CSV

### Test Results Dashboard
Summary of all test runs:
- Pass/fail counts per test
- History of test results over time
- Failed rows viewer (when `--store-failures` is used)
- Click a test to see the generated SQL

### Scheduler UI
Visual interface for the built-in KelpMesh scheduler:
- View all scheduled jobs (from `kelpmesh.yml`)
- Enable/disable schedules without editing YAML
- View next run times
- Trigger a run manually
- View schedule run history

### Schema Explorer
Browse your warehouse schema alongside your KelpMesh models:
- Compare declared schema (from `schema.yml`) against actual warehouse
- Highlight drift (new columns, dropped columns, type changes)
- One-click to generate a `schema.yml` entry for a new table

## License Tiers

| Tier | Price | Users | Projects | Features |
|------|-------|-------|----------|---------|
| **Free** | $0 forever | 1 | 3 | All Core features + Studio UI, DAG view, run history |
| **Pro** | $29/user/mo | Unlimited | Unlimited | + Team sharing, SAML SSO, Slack alerts, 1-year history |
| **Business** | $79/user/mo | Unlimited | Unlimited | + Role-based access, data masking UI, audit log export, SLA monitoring |
| **Enterprise** | Contact us | Unlimited | Unlimited | + SSO/SAML, SOC 2 report, dedicated support, on-prem deploy |

KelpMesh Core (the CLI and all warehouse adapters) is **Apache 2.0** and will never require a license.

## Set a License Key

```bash
kelpmesh-studio license set km_pro_<your-key>
```

Verify:
```bash
kelpmesh-studio license status
```

License keys are validated locally using HMAC-SHA256 — no phone-home, no internet required.

## Configuration

Add to `kelpmesh.yml`:
```yaml
studio:
  port: 8501
  host: 127.0.0.1
  theme: dark          # dark | light
  allow_run: true      # allow triggering runs from the UI
  history_days: 90     # how many days of run history to show
```

## Upgrade

```bash
pip install --upgrade kelpmesh-studio
```

## Docker

```dockerfile
FROM python:3.12-slim
RUN pip install kelpmesh-studio
WORKDIR /project
COPY . .
EXPOSE 8501
CMD ["kelpmesh", "studio", "serve", "--host", "0.0.0.0"]
```
