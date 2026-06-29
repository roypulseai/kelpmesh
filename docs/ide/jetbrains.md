# JetBrains Setup (PyCharm / DataGrip / IntelliJ)

## Install the Plugin

1. Open **Settings / Preferences** → **Plugins**
2. Click **Marketplace** tab
3. Search for **KelpMesh**
4. Click **Install** and restart the IDE

Or install from disk (`.jar` file):
- **Settings** → **Plugins** → gear icon → **Install Plugin from Disk**

## Supported IDEs

| IDE | Min Version | Notes |
|-----|-------------|-------|
| PyCharm Professional | 2023.3 | Full support |
| DataGrip | 2023.3 | Best SQL experience |
| IntelliJ IDEA Ultimate | 2023.3 | Via Python plugin |
| PyCharm Community | 2023.3 | Core features only |

## Configure the Plugin

Go to **Settings** → **Tools** → **KelpMesh**:

| Setting | Description |
|---------|-------------|
| Project directory | Path to folder containing `kelpmesh.yml` |
| Active target | dev / staging / prod |
| Python interpreter | Select the venv with kelpmesh-core installed |
| Auto-format on save | Format SQL files with `kelpmesh format` |

## Features

### SQL Dialect Support
The plugin configures the IDE's SQL dialect to match your warehouse type from `kelpmesh.yml`. This enables:
- Correct syntax highlighting per warehouse
- Warehouse-specific function autocomplete
- Dialect-aware error detection

### ref() Navigation
- `Ctrl+B` on `ref('model_name')` navigates to that model
- `Alt+F7` finds all usages of a model

### Run Configurations
Create a KelpMesh run configuration:
1. **Run** → **Edit Configurations**
2. Click `+` → **KelpMesh**
3. Set: command (`run`, `test`, `build`), models, flags
4. Click **Run** or assign a keyboard shortcut

### DataGrip Integration
DataGrip users get an extra layer:
- Connect DataGrip to your warehouse using the same credentials as `kelpmesh.yml`
- KelpMesh tables show up in the Database Explorer
- Run `kelpmesh preview <model>` output inline in a DataGrip result tab

### Lineage Tool Window
**View** → **Tool Windows** → **KelpMesh Lineage**:
- Visual DAG rendered in a tool window
- Click nodes to navigate to model files
- Export as SVG or PNG

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Run current model | `Ctrl+Shift+F10` |
| Run all tests | `Ctrl+Shift+F10` (from test file) |
| Format file | `Ctrl+Alt+L` |
| Refresh project index | `Ctrl+Shift+Alt+R` |
