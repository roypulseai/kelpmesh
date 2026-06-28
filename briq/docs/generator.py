from pathlib import Path
import json
from datetime import datetime
from briq.core.project import Project
from briq.parser.sql import SQLParser
from briq.parser.lineage import LineageExplorer


class DocsGenerator:
    def __init__(self, project: Project):
        self.project = project
        self.parser = SQLParser()
        self.lineage = LineageExplorer(project)

    def generate(self, output_dir: Path | None = None) -> str:
        if output_dir is None:
            output_dir = self.project.path / "target" / "docs"
        output_dir.mkdir(parents=True, exist_ok=True)

        models_data = []
        for name, model in self.project.models.items():
            columns = self.parser.extract_columns(model.sql)
            enriched_columns = []
            for col in columns:
                col_lineage = self.lineage.column_lineage(name, col["name"])
                enriched_columns.append({
                    **col,
                    "sources": col_lineage[0]["sources"] if col_lineage else [],
                })
            models_data.append({
                "name": name,
                "description": model.description or "",
                "materialized": model.materialized,
                "path": str(model.file_path.relative_to(self.project.path)),
                "upstream": sorted(model.upstream),
                "downstream": sorted(model.downstream),
                "columns": enriched_columns,
                "sql": model.sql,
            })

        html = self._build_html(models_data)
        index_path = output_dir / "index.html"
        index_path.write_text(html, encoding="utf-8")

        json_path = output_dir / "manifest.json"
        json_path.write_text(
            json.dumps({"models": models_data, "generated_at": datetime.now().isoformat()}, indent=2),
            encoding="utf-8",
        )

        return str(index_path)

    def _build_html(self, models: list[dict]) -> str:
        model_cards = ""
        for m in models:
            cols = ""
            for c in m["columns"]:
                sources = c.get("sources", [])
                src_str = ", ".join(
                    f"{s['table']}.{s['column']}" for s in sources
                ) or "<em>literal/expression</em>"
                cols += (
                    f"<tr>"
                    f"<td>{c['name']}</td>"
                    f"<td><code>{c['expression'][:80]}</code></td>"
                    f"<td style='font-size:0.8rem;color:#888'>{src_str}</td>"
                    f"</tr>"
                )

            upstream = ", ".join(
                f'<a href="#{u}">{u}</a>' for u in m["upstream"]
            ) or "<em>source</em>"
            downstream = ", ".join(
                f'<a href="#{d}">{d}</a>' for d in m["downstream"]
            ) or "<em>none</em>"

            model_cards += f"""
            <div class="model-card" id="{m['name']}">
                <h2>{m['name']}</h2>
                <p class="desc">{m['description'] or 'No description'}</p>
                <div class="meta">
                    <span class="badge">{m['materialized']}</span>
                    <span class="path">{m['path']}</span>
                </div>
                <div class="lineage">
                    <div class="up">Upstream: {upstream}</div>
                    <div class="down">Downstream: {downstream}</div>
                </div>
                <details open>
                    <summary>Columns ({len(m['columns'])})</summary>
                    <table>
                        <thead><tr><th>Column</th><th>Expression</th><th>Sources</th></tr></thead>
                        <tbody>{cols}</tbody>
                    </table>
                </details>
                <details>
                    <summary>SQL</summary>
                    <pre><code>{m['sql']}</code></pre>
                </details>
            </div>
            """

        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>briq documentation</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
.header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; text-align: center; }}
.header h1 {{ font-size: 2rem; }}
.header p {{ opacity: 0.9; }}
.container {{ max-width: 1000px; margin: 0 auto; padding: 1rem; }}
.model-card {{ background: white; border-radius: 8px; padding: 1.5rem; margin: 1rem 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.model-card h2 {{ margin-bottom: 0.5rem; }}
.desc {{ color: #666; margin-bottom: 0.5rem; }}
.meta {{ display: flex; gap: 0.5rem; margin-bottom: 1rem; }}
.badge {{ background: #667eea; color: white; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.8rem; }}
.path {{ color: #999; font-size: 0.8rem; }}
.lineage {{ font-size: 0.9rem; color: #555; margin-bottom: 1rem; }}
.lineage a {{ color: #667eea; text-decoration: none; }}
.lineage a:hover {{ text-decoration: underline; }}
details {{ margin-top: 0.5rem; }}
summary {{ cursor: pointer; color: #667eea; font-weight: 500; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 0.5rem; }}
th, td {{ text-align: left; padding: 0.4rem; border-bottom: 1px solid #eee; }}
th {{ font-weight: 600; color: #555; }}
pre {{ background: #1e1e1e; color: #d4d4d4; padding: 1rem; border-radius: 4px; overflow-x: auto; margin-top: 0.5rem; font-size: 0.85rem; }}
</style>
</head>
<body>
<div class="header"><h1>briq documentation</h1><p>{len(models)} models &middot; column-level lineage</p></div>
<div class="container">{model_cards}</div>
</body>
</html>"""
