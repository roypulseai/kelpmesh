# Project Structure

A typical briq project looks like this:

```
my_project/
├── briq.yml                 # Project configuration
├── classify.yml             # Data classification rules (optional)
├── security.yml             # RLS and security policies (optional)
├── .env                     # Environment variables (optional, git-ignored)
├── models/                  # SQL model directory
│   ├── staging/             # Staging models
│   │   └── stg_orders.sql
│   ├── marts/               # Business-level models
│   │   └── customer_orders.sql
│   └── example.sql          # Sample model
├── tests/                   # SQL assertion tests
│   └── assert_orders_positive.sql
├── seeds/                   # Seed SQL files
│   └── seed.sql
├── analyses/                # Ad-hoc analyses
│   └── exploratory.sql
├── snapshots/               # Snapshot models (dbt import)
├── briq_packages/           # Installed briq packages
├── target/                  # Generated output
│   ├── audit.log            # JSONL audit trail
│   ├── briq_state.duckdb    # State database
│   └── docs/                # Generated documentation
└── .gitignore
```
