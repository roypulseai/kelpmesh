# VS Code Setup

## Install the Extension

1. Open VS Code
2. Press `Ctrl+Shift+X` to open Extensions
3. Search for **KelpMesh**
4. Click **Install**

Or install from the command line:
```bash
code --install-extension kelpmesh.kelpmesh-vscode
```

## Configure the Extension

Open Settings (`Ctrl+,`) and search for `kelpmesh`:

| Setting | Default | Description |
|---------|---------|-------------|
| `kelpmesh.projectDir` | `.` | Path to your KelpMesh project root |
| `kelpmesh.target` | `dev` | Active profile (matches `kelpmesh.yml` targets) |
| `kelpmesh.autoFormat` | `false` | Format SQL on save |
| `kelpmesh.showInlineLineage` | `true` | Show upstream/downstream counts inline |

Or edit `.vscode/settings.json` directly:
```json
{
  "kelpmesh.projectDir": "${workspaceFolder}",
  "kelpmesh.target": "dev",
  "kelpmesh.autoFormat": true
}
```

## Features

### IntelliSense & Autocomplete
- `ref(` → autocomplete all model names in your project
- `source(` → autocomplete source table names from `schema.yml`
- Column names autocomplete after `SELECT ` when schema is defined

### Navigate to Definition
- `Ctrl+Click` on a `ref('model_name')` → opens that model's `.sql` file
- Works across packages in `kelpmesh_packages/`

### Run Models from the Editor
- Open any `.sql` model file
- Press `Ctrl+Shift+P` → **KelpMesh: Run This Model**
- Results appear in the integrated terminal

Keyboard shortcuts:
| Action | Shortcut |
|--------|----------|
| Run current model | `Ctrl+Shift+R` |
| Preview model (first 100 rows) | `Ctrl+Shift+P` then "KelpMesh: Preview" |
| Run tests for model | `Ctrl+Shift+T` |
| Format file | `Shift+Alt+F` |
| Open lineage view | `Ctrl+Shift+L` |

### Inline Docs Preview
Hover over a `ref('model')` to see:
- Model description from `schema.yml`
- Column list
- Tags

### Lineage Sidebar
Click the KelpMesh icon in the Activity Bar to open the Lineage panel:
- Visual DAG of your project
- Click any node to open the model file
- Filter by tag or materialization type

### Lint on Save
When `kelpmesh.autoFormat: true`:
- SQL files are auto-formatted with `kelpmesh format` on save
- Lint warnings appear in the Problems panel (`Ctrl+Shift+M`)

## Troubleshooting

**Extension not finding models:**
- Verify `kelpmesh.projectDir` points to the folder containing `kelpmesh.yml`
- Run `kelpmesh debug` in the terminal to confirm the project loads

**Autocomplete not working:**
- The extension indexes models on load. Run `Ctrl+Shift+P` → **KelpMesh: Refresh Index**

**"kelpmesh not found" error:**
- Make sure the virtual environment with kelpmesh installed is selected as your Python interpreter (`Ctrl+Shift+P` → "Python: Select Interpreter")
