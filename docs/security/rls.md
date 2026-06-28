# Row-Level Security (RLS)

Restrict which rows a role can see by defining filter policies. Filters are injected at query time — never modify base tables.

## Configuration

Create a `security.yml` file in your project root:

```yaml
# security.yml
rls:
  orders:
    viewer: "region = current_setting('app.region')"
    editor: "1=1"
  users:
    viewer: "is_active = true"
    admin: "1=1"
```

Alternatively, RLS policies can be defined in `kelpmesh.yml` under `rls:` or `security.rls:`.

## CLI Usage

```bash
# List all RLS policies
KelpMesh security rls

# Generate stub security.yml
KelpMesh security rls --init
```
