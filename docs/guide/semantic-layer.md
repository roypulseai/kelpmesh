# Semantic layer

The briq semantic layer lets you define business metrics once and expose them to any BI tool. Define a metric in YAML, and briq generates the SQL and exports it to Looker, Tableau, Power BI, or QlikSense — no manual rework required.

---

## Defining metrics

Metrics live in `metrics.yml` inside your project:

```yaml
version: 1

metrics:
  - name: total_revenue
    label: "Total Revenue"
    model: orders_daily
    type: simple
    measure: SUM(amount)
    dimensions:
      - customer_id
      - order_date
    filters:
      - "status != 'cancelled'"
    format_string: "$#,##0.00"
    tags:
      - finance

  - name: revenue_per_customer
    label: "Revenue per Customer"
    type: ratio
    numerator: SUM(amount)
    denominator: COUNT(DISTINCT customer_id)
    model: orders_daily
    format_string: "$#,##0.00"

  - name: avg_order_value
    label: "Average Order Value"
    type: derived
    expression: "{{total_revenue}} / {{order_count}}"
    format_string: "$#,##0"
```

---

## Metric types

| Type | Description | Required fields |
|---|---|---|
| `simple` | A single aggregation on one model | `measure`, `model` |
| `ratio` | Numerator ÷ denominator | `numerator`, `denominator`, `model` |
| `derived` | Expression referencing other metrics | `expression` (uses `{{metric_name}}` refs) |

---

## Generating SQL

```bash
# Preview the SQL for a metric
briq metric sql total_revenue

# With filters and grouping
briq metric sql total_revenue --group-by order_date --where "region='EMEA'"
```

---

## Exporting to BI tools

```bash
# Export all formats to ./exports/
briq export --format all --output ./exports/

# Export a specific format
briq export --format looker --output ./looker/
briq export --format powerbi --output ./powerbi/
briq export --format tableau --output ./tableau/
briq export --format qlik --output ./qlik/
```

### Looker

Generates `.view.lkml` and `.explore.lkml` files — one pair per model. Import them into your LookML project.

### Tableau

Generates `.tds` data source XML files. Open them in Tableau Desktop or upload to Tableau Server.

### Power BI

Generates a `.bim` Tabular Model JSON file (Analysis Services format, `compatibilityLevel: 1550`) plus a `measures.dax` file with all DAX measure definitions. Import the `.bim` via Tabular Editor or SQL Server Management Studio.

### QlikSense

Generates `master_items.json` (master measures + dimensions) and `load_script.qvs`. Import via the QlikSense Management Console.

---

## REST API (briq serve)

Expose metrics over HTTP for custom integrations:

```bash
briq serve --host 0.0.0.0 --port 8080
```

### Endpoints

```
GET /metrics
```
Returns all defined metrics.

```
GET /metrics/{name}/sql?group_by=order_date&where=region='EMEA'&limit=1000
```
Returns the generated SQL for a metric (simple types only).

```
GET /export/{format}
```
Returns the export payload for `looker`, `tableau`, `powerbi`, `qlik`, or `manifest`.

```
GET /health
```
Returns `{"status": "ok"}`.

---

## Semantic manifest

Export a machine-readable manifest of all metrics and sources:

```bash
briq export --format manifest --output ./
```

This produces `semantic_manifest.json` — useful for building internal metric catalogues, auditing coverage, or feeding downstream tooling.
