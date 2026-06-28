from pathlib import Path
import json
from datetime import datetime
from kelpmesh.core.project import Project
from kelpmesh.core.schema_yaml import SchemaYaml
from kelpmesh.parser.sql import SQLParser
from kelpmesh.parser.lineage import LineageExplorer


class DocsGenerator:
    def __init__(self, project: Project):
        self.project = project
        self.parser = SQLParser()
        self.lineage = LineageExplorer(project)
        self.schema = SchemaYaml(project.path)

    def generate(self, output_dir: Path | None = None) -> str:
        if output_dir is None:
            output_dir = self.project.path / "target" / "docs"
        output_dir.mkdir(parents=True, exist_ok=True)

        models_data = []
        for name, model in self.project.models.items():
            sql_cols = self.parser.extract_columns(model.sql or "")
            yaml_col_descs = self.schema.column_descriptions(name)
            yaml_col_meta = {c["name"]: c for c in self.schema.column_metadata(name)}

            enriched_columns = []
            seen = set()
            for col in sql_cols:
                cname = col["name"]
                seen.add(cname)
                col_lineage = self.lineage.column_lineage(name, cname)
                meta = yaml_col_meta.get(cname, {})
                enriched_columns.append({
                    **col,
                    "description": meta.get("description") or yaml_col_descs.get(cname, ""),
                    "data_type": meta.get("data_type", ""),
                    "sources": col_lineage[0]["sources"] if col_lineage else [],
                })

            # Add columns declared in schema.yml but not found in SQL parse
            for cname, meta in yaml_col_meta.items():
                if cname not in seen:
                    enriched_columns.append({
                        "name": cname,
                        "expression": "",
                        "description": meta.get("description", ""),
                        "data_type": meta.get("data_type", ""),
                        "sources": [],
                    })

            model_desc = (
                model.description
                or self.schema.model_description(name)
                or ""
            )

            models_data.append({
                "name": name,
                "description": model_desc,
                "materialized": model.materialized,
                "path": str(model.file_path.relative_to(self.project.path)),
                "tags": model.tags or self.schema.model_tags(name),
                "upstream": sorted(model.upstream),
                "downstream": sorted(model.downstream),
                "columns": enriched_columns,
                "sql": model.sql or "",
            })

        html = self._build_html(models_data)
        index_path = output_dir / "index.html"
        index_path.write_text(html, encoding="utf-8")

        manifest = {
            "models": models_data,
            "generated_at": datetime.now().isoformat(),
            "project": self.project.config.name,
        }
        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        return str(index_path)

    # ── HTML builder ──────────────────────────────────────────────────────

    def _build_html(self, models: list[dict]) -> str:
        dag_data = self._dag_json(models)
        model_cards = "".join(self._model_card(m) for m in models)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{self.project.config.name} — kelpmesh docs</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f8f9fa;color:#1a1a2e;line-height:1.6}}
a{{color:#5c6bc0;text-decoration:none}}a:hover{{text-decoration:underline}}
.header{{background:linear-gradient(135deg,#5c6bc0 0%,#3949ab 100%);color:#fff;padding:2rem 2.5rem}}
.header h1{{font-size:1.6rem;font-weight:700}}.header p{{opacity:.85;font-size:.9rem;margin-top:.25rem}}
.layout{{display:grid;grid-template-columns:240px 1fr;min-height:calc(100vh - 100px)}}
.sidebar{{background:#fff;border-right:1px solid #e8eaf6;padding:1rem 0;position:sticky;top:0;height:calc(100vh - 100px);overflow-y:auto}}
.sidebar-section{{padding:.5rem 1rem .25rem;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#9fa8da}}
.sidebar-item{{display:block;padding:.3rem 1rem .3rem 1.5rem;font-size:.82rem;color:#3d4166;border-left:2px solid transparent;transition:all .15s}}
.sidebar-item:hover,.sidebar-item.active{{background:#f0f2ff;border-left-color:#5c6bc0;color:#5c6bc0;text-decoration:none}}
.mat-badge{{font-size:.6rem;padding:.1rem .35rem;border-radius:3px;margin-left:.3rem;font-weight:600;vertical-align:middle}}
.mat-view{{background:#e8f5e9;color:#2e7d32}}.mat-table{{background:#e3f2fd;color:#1565c0}}
.mat-incremental{{background:#fff8e1;color:#f57f17}}.mat-snapshot{{background:#fce4ec;color:#c62828}}
.mat-ephemeral{{background:#f3e5f5;color:#6a1b9a}}
.main{{padding:1.5rem 2rem;max-width:900px}}
.dag-section{{background:#fff;border:1px solid #e8eaf6;border-radius:8px;padding:1.25rem;margin-bottom:1.5rem}}
.dag-section h2{{font-size:.9rem;font-weight:700;color:#3d4166;margin-bottom:.75rem}}
#dag-canvas{{width:100%;height:260px;display:block}}
.model-card{{background:#fff;border:1px solid #e8eaf6;border-radius:8px;padding:1.25rem;margin-bottom:1rem;scroll-margin-top:1rem}}
.model-card h2{{font-size:1.1rem;font-weight:700;margin-bottom:.25rem}}
.model-desc{{color:#666;font-size:.85rem;margin-bottom:.75rem}}
.model-meta{{display:flex;align-items:center;gap:.5rem;margin-bottom:.75rem;flex-wrap:wrap}}
.tag{{font-size:.65rem;background:#f0f2ff;color:#5c6bc0;padding:.1rem .4rem;border-radius:3px;font-weight:600}}
.model-path{{color:#aaa;font-size:.75rem}}
.lineage-row{{font-size:.82rem;color:#555;margin-bottom:.75rem}}
.lineage-row span{{font-weight:600;color:#3d4166}}
details{{margin-top:.5rem}}summary{{cursor:pointer;color:#5c6bc0;font-size:.85rem;font-weight:600;user-select:none;padding:.25rem 0}}
summary:hover{{color:#3949ab}}
table{{width:100%;border-collapse:collapse;margin-top:.5rem;font-size:.82rem}}
th{{text-align:left;padding:.35rem .5rem;background:#f8f9fa;color:#666;font-weight:600;border-bottom:2px solid #e8eaf6}}
td{{padding:.3rem .5rem;border-bottom:1px solid #f0f2ff;vertical-align:top}}
td code{{background:#f0f2ff;padding:.1rem .3rem;border-radius:3px;font-size:.78rem;color:#3d4166}}
.src-col{{font-size:.75rem;color:#9fa8da}}
.desc-col{{color:#555}}
.no-desc{{color:#ccc;font-style:italic}}
pre{{background:#1e1e2e;color:#cdd6f4;padding:1rem;border-radius:6px;overflow-x:auto;margin-top:.5rem;font-size:.8rem;line-height:1.5}}
</style>
</head>
<body>
<div class="header">
  <h1>{self.project.config.name}</h1>
  <p>{len(models)} models &nbsp;·&nbsp; kelpmesh docs &nbsp;·&nbsp; column-level lineage</p>
</div>
<div class="layout">
  <nav class="sidebar">
    <div class="sidebar-section">Models</div>
    {"".join(self._sidebar_item(m) for m in models)}
  </nav>
  <main class="main">
    <div class="dag-section">
      <h2>Lineage DAG</h2>
      <canvas id="dag-canvas"></canvas>
    </div>
    {model_cards}
  </main>
</div>
<script>
// ── Inline DAG renderer (no external deps) ────────────────────────────────
(function(){{
  const DAG = {dag_data};
  const canvas = document.getElementById('dag-canvas');
  const dpr = window.devicePixelRatio || 1;
  function resize() {{
    canvas.width  = canvas.offsetWidth  * dpr;
    canvas.height = canvas.offsetHeight * dpr;
    draw();
  }}
  window.addEventListener('resize', resize);

  // Topological layer assignment
  function layers(nodes, edges) {{
    const inDeg = {{}};
    nodes.forEach(n => inDeg[n] = 0);
    edges.forEach(([a, b]) => inDeg[b] = (inDeg[b] || 0) + 1);
    const layer = {{}};
    const queue = nodes.filter(n => !inDeg[n]);
    queue.forEach(n => layer[n] = 0);
    let head = 0;
    while (head < queue.length) {{
      const n = queue[head++];
      edges.filter(([a]) => a === n).forEach(([, b]) => {{
        layer[b] = Math.max(layer[b] || 0, layer[n] + 1);
        inDeg[b]--;
        if (inDeg[b] === 0) queue.push(b);
      }});
    }}
    return layer;
  }}

  function draw() {{
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const W = canvas.offsetWidth, H = canvas.offsetHeight;
    ctx.clearRect(0, 0, W, H);

    const nodes = DAG.nodes, edges = DAG.edges;
    if (!nodes.length) return;

    const layerMap = layers(nodes, edges);
    const maxLayer = Math.max(...Object.values(layerMap));
    const byLayer = {{}};
    nodes.forEach(n => {{
      const l = layerMap[n] || 0;
      (byLayer[l] = byLayer[l] || []).push(n);
    }});

    const PAD = 20, BW = 130, BH = 30, GAP_X = 60, GAP_Y = 12;
    const cols = maxLayer + 1;
    const maxInCol = Math.max(...Object.values(byLayer).map(a => a.length));
    const totalH = maxInCol * (BH + GAP_Y) - GAP_Y;
    const totalW = cols * BW + (cols - 1) * GAP_X;
    const offX = Math.max(PAD, (W - totalW) / 2);
    const offY = Math.max(PAD, (H - totalH) / 2);

    const pos = {{}};
    Object.entries(byLayer).forEach(([l, ns]) => {{
      const x = offX + +l * (BW + GAP_X);
      const colH = ns.length * (BH + GAP_Y) - GAP_Y;
      const startY = offY + (totalH - colH) / 2;
      ns.forEach((n, i) => {{
        pos[n] = {{ x, y: startY + i * (BH + GAP_Y), w: BW, h: BH }};
      }});
    }});

    // Edges
    ctx.strokeStyle = '#c5cae9';
    ctx.lineWidth = 1.5;
    edges.forEach(([a, b]) => {{
      const pa = pos[a], pb = pos[b];
      if (!pa || !pb) return;
      const ax = pa.x + pa.w, ay = pa.y + pa.h / 2;
      const bx = pb.x,        by = pb.y + pb.h / 2;
      const cx = (ax + bx) / 2;
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.bezierCurveTo(cx, ay, cx, by, bx, by);
      ctx.stroke();
      // Arrow
      ctx.fillStyle = '#c5cae9';
      ctx.beginPath();
      ctx.moveTo(bx, by);
      ctx.lineTo(bx - 7, by - 4);
      ctx.lineTo(bx - 7, by + 4);
      ctx.closePath();
      ctx.fill();
    }});

    // Boxes
    nodes.forEach(n => {{
      const p = pos[n];
      if (!p) return;
      ctx.fillStyle = '#eef0fb';
      ctx.strokeStyle = '#9fa8da';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(p.x, p.y, p.w, p.h, 5);
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#3d4166';
      ctx.font = `600 11px -apple-system,sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      const label = n.length > 16 ? n.slice(0,14)+'..' : n;
      ctx.fillText(label, p.x + p.w / 2, p.y + p.h / 2);
    }});
  }}

  canvas.addEventListener('click', function(e) {{
    const rect = canvas.getBoundingClientRect();
    const mx = (e.clientX - rect.left), my = (e.clientY - rect.top);
    // Re-derive positions (lightweight)
    const nodes = DAG.nodes, edges = DAG.edges;
    const layerMap = layers(nodes, edges);
    const byLayer = {{}};
    nodes.forEach(n => {{ const l = layerMap[n]||0; (byLayer[l]=byLayer[l]||[]).push(n); }});
    const maxLayer = Math.max(...Object.values(layerMap));
    const W = canvas.offsetWidth, H = canvas.offsetHeight;
    const PAD=20,BW=130,BH=30,GAP_X=60,GAP_Y=12;
    const cols = maxLayer+1;
    const maxInCol = Math.max(...Object.values(byLayer).map(a=>a.length));
    const totalH = maxInCol*(BH+GAP_Y)-GAP_Y;
    const totalW = cols*BW+(cols-1)*GAP_X;
    const offX = Math.max(PAD,(W-totalW)/2), offY = Math.max(PAD,(H-totalH)/2);
    const pos = {{}};
    Object.entries(byLayer).forEach(([l,ns])=>{{
      const x=offX+ +l*(BW+GAP_X);
      const colH=ns.length*(BH+GAP_Y)-GAP_Y;
      const startY=offY+(totalH-colH)/2;
      ns.forEach((n,i)=>{{ pos[n]={{x,y:startY+i*(BH+GAP_Y),w:BW,h:BH}}; }});
    }});
    for (const [n,p] of Object.entries(pos)) {{
      if (mx>=p.x && mx<=p.x+p.w && my>=p.y && my<=p.y+p.h) {{
        const el = document.getElementById(n);
        if (el) {{ el.scrollIntoView({{behavior:'smooth',block:'start'}}); }}
        break;
      }}
    }}
  }});

  if (typeof ResizeObserver !== 'undefined') {{
    new ResizeObserver(resize).observe(canvas);
  }} else {{ resize(); }}
  resize();
}})();

// Sidebar active link on scroll
const cards = document.querySelectorAll('.model-card');
const links = document.querySelectorAll('.sidebar-item');
const observer = new IntersectionObserver(entries => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      links.forEach(l => l.classList.toggle('active', l.getAttribute('href') === '#' + e.target.id));
    }}
  }});
}}, {{threshold: 0.4}});
cards.forEach(c => observer.observe(c));
</script>
</body>
</html>"""

    def _dag_json(self, models: list[dict]) -> str:
        nodes = [m["name"] for m in models]
        edges = []
        for m in models:
            for up in m["upstream"]:
                if up in {n for n in nodes}:
                    edges.append([up, m["name"]])
        return json.dumps({"nodes": nodes, "edges": edges})

    def _sidebar_item(self, m: dict) -> str:
        mat = m["materialized"]
        badge = f'<span class="mat-badge mat-{mat}">{mat[0].upper()}</span>'
        return (
            f'<a class="sidebar-item" href="#{m["name"]}">'
            f'{m["name"]}{badge}'
            f'</a>\n'
        )

    def _model_card(self, m: dict) -> str:
        # Tags
        tag_html = "".join(f'<span class="tag">{t}</span>' for t in (m.get("tags") or []))
        mat = m["materialized"]
        mat_badge = f'<span class="mat-badge mat-{mat}">{mat}</span>'

        # Lineage
        upstream = ", ".join(
            f'<a href="#{u}">{u}</a>' for u in m["upstream"]
        ) or "<em style='color:#ccc'>none</em>"
        downstream = ", ".join(
            f'<a href="#{d}">{d}</a>' for d in m["downstream"]
        ) or "<em style='color:#ccc'>none</em>"

        # Column table
        col_rows = ""
        for c in m["columns"]:
            sources = c.get("sources", [])
            src_str = ", ".join(
                f"{s['table']}.{s['column']}" for s in sources
            ) if sources else ""
            desc = c.get("description", "") or ""
            dtype = c.get("data_type", "") or ""
            expr = (c.get("expression") or "")[:80]
            col_rows += (
                f"<tr>"
                f"<td><strong>{c['name']}</strong>"
                + (f"<br><span style='font-size:.7rem;color:#aaa'>{dtype}</span>" if dtype else "")
                + f"</td>"
                f"<td class='desc-col'>{desc or '<span class=\"no-desc\">—</span>'}</td>"
                f"<td><code>{expr}</code></td>"
                f"<td class='src-col'>{src_str}</td>"
                f"</tr>"
            )

        return f"""
<div class="model-card" id="{m['name']}">
  <h2>{m['name']}</h2>
  <p class="model-desc">{m['description'] or '<em style=\"color:#ccc\">No description</em>'}</p>
  <div class="model-meta">
    {mat_badge}
    {tag_html}
    <span class="model-path">{m['path']}</span>
  </div>
  <div class="lineage-row">
    <span>Upstream:</span> {upstream} &nbsp;|&nbsp; <span>Downstream:</span> {downstream}
  </div>
  <details open>
    <summary>Columns ({len(m['columns'])})</summary>
    <table>
      <thead><tr><th>Column</th><th>Description</th><th>Expression</th><th>Sources</th></tr></thead>
      <tbody>{col_rows}</tbody>
    </table>
  </details>
  <details>
    <summary>SQL</summary>
    <pre>{m['sql']}</pre>
  </details>
</div>"""
