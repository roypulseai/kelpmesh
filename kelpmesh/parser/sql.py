__all__ = ["SQLParser"]

import logging

import sqlglot
from sqlglot import exp

_logger = logging.getLogger(__name__)


class SQLParser:
    def extract_table_references(self, sql: str) -> list[str]:
        """Return external table references — CTE aliases (internal WITH clauses) are excluded.

        Previously, CTE aliases like `WITH orders AS (...)` would be added as outgoing
        dependency edges, which created false circular-dependency cycles when a CTE
        name collided with a real model name (e.g. `orders.sql` had a CTE named `orders`).
        Now CTE aliases are collected up-front and used to *exclude* internal references.
        """
        tables: list[str] = []
        try:
            parsed = sqlglot.parse(sql)
            if not parsed:
                return tables
            for statement in parsed:
                if statement is None:
                    continue
                cte_aliases = self._collect_cte_aliases(statement)
                self._extract_from_tables(statement, tables, cte_aliases=cte_aliases)
        except Exception as e:
            _logger.debug("extract_table_references parse error: %s", e)
        return list(dict.fromkeys(tables))

    def extract_source_references(self, sql: str) -> list[str]:
        """Extract source('name', 'table') references from SQL."""
        sources = []
        try:
            parsed = sqlglot.parse(sql)
            if not parsed:
                return sources
            for statement in parsed:
                if statement is None:
                    continue
                for node in statement.find_all(exp.Anonymous):
                    if node.name.lower() == "source" and len(node.expressions) >= 1:
                        first = node.expressions[0]
                        if isinstance(first, exp.Literal):
                            sources.append(first.this)
        except Exception as e:
            _logger.debug("extract_source_references parse error: %s", e)
        return list(dict.fromkeys(sources))

    def _extract_from_tables(self, node, tables: list[str], cte_aliases: set[str] | None = None):
        if cte_aliases is None:
            cte_aliases = set()
        for table in node.find_all(exp.Table):
            # A reference to a CTE defined in the same statement is internal — not an external dep.
            if table.name and table.name not in cte_aliases:
                tables.append(table.name)

    def _collect_cte_aliases(self, statement) -> set[str]:
        """Collect all CTE alias names declared with WITH ... AS (...) in the statement.

        These are *internal* scoping names — they should never create outgoing
        dependency edges in the DAG. Used to filter them out of the table reference list.
        """
        cte_aliases: set[str] = set()
        for cte in statement.find_all(exp.CTE):
            # sqlglot exposes the CTE name via .alias (preferred) or .args["alias"]
            alias = cte.alias or (cte.args.get("alias").name if cte.args.get("alias") else None)
            if alias:
                cte_aliases.add(alias)
        return cte_aliases

    def extract_columns(self, sql: str) -> list[dict]:
        columns = []
        try:
            parsed = sqlglot.parse(sql)
            if not parsed:
                return columns
            for statement in parsed:
                if statement is None:
                    continue
                for select in statement.find_all(exp.Select):
                    for e in select.expressions:
                        alias = e.alias or e.output_name or str(e)
                        columns.append({
                            "name": alias,
                            "expression": str(e),
                        })
        except Exception as e:
            _logger.debug("extract_columns parse error: %s", e)
        return columns

    def transpile(self, sql: str, dialect: str = "duckdb") -> str:
        try:
            result = sqlglot.transpile(sql, read="duckdb", write=dialect)
            return "\n".join(result) if result else sql
        except Exception as e:
            _logger.debug("transpile error: %s", e)
            return sql

    def normalize(self, sql: str) -> str:
        try:
            parsed = sqlglot.parse(sql)
            if parsed and parsed[0]:
                return parsed[0].sql(dialect="duckdb")
            return sql
        except Exception as e:
            _logger.debug("normalize error: %s", e)
            return sql
