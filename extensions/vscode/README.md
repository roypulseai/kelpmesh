# KelpMesh for VS Code

Code-native data transformation — SQL and Python models, no Jinja required.

Run models, preview data, view lineage, and plan changes without leaving VS Code.

## Features

- **Run / Test / Build / Preview / Compile / Plan** — CodeLens buttons above each .sql or .py model file
- **Model tree view** in the sidebar — all models in your project, with refresh and plan actions
- **37 SQL snippets** — surrogate_key, safe_divide, datediff, haversine, and more
- **PII scan** — detect sensitive columns in any model
- **Open Studio** — launch the browser dashboard (kelpmesh studio) from the command palette

## Requirements

Install the KelpMesh CLI:

```bash
pip install KelpMesh
```

## Quick Start

1. Open a folder containing a kelpmesh.yml project (or run kelpmesh init)
2. Open any .sql file in models/ — you'll see Run / Test / Preview buttons above it
3. Use the sidebar tree to browse all models
4. Run KelpMesh: Plan (dry run) to see what would change before running

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| kelpmesh.pythonPath | "" | Python executable with KelpMesh installed. Blank = workspace interpreter. |
| kelpmesh.projectDir | "" | Path to project root (folder with kelpmesh.yml). Blank = workspace root. |
| kelpmesh.autoRunOnSave | alse | Auto-run model on save. |
| kelpmesh.showCodeLens | 	rue | Show Run / Test / Preview buttons above model files. |

## License

Apache 2.0