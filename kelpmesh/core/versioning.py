"""Model versioning — allows models to declare explicit version numbers.

Usage in a model SQL file (header comment):
    -- version: 2
    -- defined_in: customers      (the canonical base name)
    -- materialized: table

Or in schema.yml under a model:
    models:
      - name: customers_v2
        config:
          version: 2
          defined_in: customers
          latest_version: 2

Versioned models:
  - Are stored as ``<name>_v<N>`` in the warehouse by default.
  - ``ref('customers')``            → resolves to the latest version's table.
  - ``ref('customers', version=1)`` → resolves to ``customers_v1``.
  - Older versions remain in the warehouse until explicitly dropped.

Registration is handled by :func:`register_versions` which is called by
``Project._load_models()`` after all models have been parsed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kelpmesh.core.model import BriqModel


def register_versions(models: dict[str, "BriqModel"]) -> None:
    """Scan *models* and wire up version metadata.

    For each model that declares ``version``:
      - Set its ``table_name`` to ``<defined_in>_v<N>`` (or ``<name>_v<N>``).
      - Compute ``latest_version`` on all models sharing the same base name.
      - Set ``alias`` so the executor writes to the versioned table name.
    """
    # Group versioned models by their canonical name
    version_groups: dict[str, list["BriqModel"]] = {}

    for model in models.values():
        if model.version is not None:
            base = model.defined_in or _strip_version_suffix(model.name)
            version_groups.setdefault(base, []).append(model)

    for base_name, versioned in version_groups.items():
        if not versioned:
            continue
        # Determine the latest version
        max_version = max(m.version for m in versioned)  # type: ignore[arg-type]

        for m in versioned:
            # Physical table name: <base>_v<N>
            versioned_alias = f"{base_name}_v{m.version}"
            if not m.alias:
                m.alias = versioned_alias

            # Propagate latest_version to all variants
            m.latest_version = max_version

        # Also update the un-versioned "latest" model if it exists
        if base_name in models:
            latest_model = models[base_name]
            latest_model.latest_version = max_version
            # Point it at the latest versioned table so ref('model') works
            if not latest_model.alias:
                latest_model.alias = f"{base_name}_v{max_version}"


def _strip_version_suffix(name: str) -> str:
    """Remove trailing _v<N> from a model name, if present."""
    import re
    return re.sub(r"_v\d+$", "", name)


def resolve_ref(
    models: dict[str, "BriqModel"],
    name: str,
    version: int | None = None,
) -> str:
    """Return the physical table name for a ref() call.

    Used by the SQL parser and executor to resolve ``ref('name')`` and
    ``ref('name', version=N)``.
    """
    if version is not None:
        # Look for explicit versioned model
        versioned_name = f"{name}_v{version}"
        if versioned_name in models:
            model = models[versioned_name]
            return model.alias or model.relation_name
        # Fall back to alias on any model with matching base + version
        for m in models.values():
            if m.version == version and (m.defined_in == name or _strip_version_suffix(m.name) == name):
                return m.alias or m.relation_name
        return versioned_name  # best-effort

    # No version requested → use latest
    model = models.get(name)
    if model:
        return model.alias or model.relation_name
    return name
