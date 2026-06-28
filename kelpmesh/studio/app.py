"""Minimal bundled kelpmesh Studio — FastAPI backend + inline HTML dashboard.

No external kelpmesh_studio package required. Works with: pip install kelpmesh[studio]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>kelpmesh Studio</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #0f0f0f; --surface: #1a1a1a; --border: #2a2a2a;
      --text: #e8e8e8; --muted: #888; --accent: #5b8dee;
      --green: #4ade80; --yellow: #fbbf24; --red: #f87171;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    body { background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; display: flex; height: 100vh; overflow: hidden; }
    #sidebar { width: 220px; background: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; flex-shrink: 0; }
    #sidebar header { padding: 20px 16px 12px; border-bottom: 1px solid var(--border); }
    #sidebar header h1 { font-size: 16px; font-weight: 600; color: var(--accent); letter-spacing: -0.3px; }
    #sidebar header p { font-size: 11px; color: var(--muted); margin-top: 2px; }
    #nav { padding: 8px 0; flex: 1; overflow-y: auto; }
    .nav-item { display: block; padding: 8px 16px; cursor: pointer; color: var(--muted); font-size: 13px; border-left: 2px solid transparent; transition: all 0.1s; }
    .nav-item:hover { color: var(--text); background: rgba(255,255,255,0.04); }
    .nav-item.active { color: var(--text); border-left-color: var(--accent); background: rgba(91,141,238,0.08); }
    #main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
    #topbar { padding: 12px 20px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 12px; }
    #topbar h2 { font-size: 15px; font-weight: 600; flex: 1; }
    .btn { padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border); background: var(--surface); color: var(--text); font-size: 12px; cursor: pointer; transition: all 0.1s; }
    .btn:hover { background: #252525; border-color: #3a3a3a; }
    .btn.primary { background: var(--accent); border-color: var(--accent); color: white; }
    .btn.primary:hover { background: #4a7ee0; }
    #content { flex: 1; overflow-y: auto; padding: 20px; }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 12px; }
    .card h3 { font-size: 13px; font-weight: 600; margin-bottom: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
    .model-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
    .model-card { background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 12px; cursor: pointer; transition: border-color 0.1s; }
    .model-card:hover { border-color: var(--accent); }
    .model-name { font-size: 13px; font-weight: 500; }
    .model-type { font-size: 11px; margin-top: 4px; }
    .tag { display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 500; }
    .tag.view { background: rgba(91,141,238,0.15); color: var(--accent); }
    .tag.table { background: rgba(74,222,128,0.15); color: var(--green); }
    .tag.incremental { background: rgba(251,191,36,0.15); color: var(--yellow); }
    .tag.analysis { background: rgba(136,136,136,0.15); color: var(--muted); }
    .stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
    .stat { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }
    .stat-val { font-size: 24px; font-weight: 700; }
    .stat-label { font-size: 11px; color: var(--muted); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
    .run-row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border); }
    .run-row:last-child { border-bottom: none; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .status-dot.success { background: var(--green); }
    .status-dot.failed { background: var(--red); }
    .status-dot.skipped { background: var(--muted); }
    .run-name { flex: 1; font-size: 13px; }
    .run-time { font-size: 11px; color: var(--muted); }
    #toast { position: fixed; bottom: 20px; right: 20px; background: var(--accent); color: white; padding: 10px 18px; border-radius: 8px; font-size: 13px; display: none; z-index: 999; }
    .empty { color: var(--muted); font-size: 13px; text-align: center; padding: 40px; }
    #dag-container { width: 100%; height: 400px; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; position: relative; }
    svg text { fill: var(--text); font-family: var(--font); font-size: 12px; }
  </style>
</head>
<body>
  <aside id="sidebar">
    <header>
      <h1>kelpmesh Studio</h1>
      <p id="proj-name">Loading...</p>
    </header>
    <nav id="nav">
      <a class="nav-item active" onclick="showPage('overview')">Overview</a>
      <a class="nav-item" onclick="showPage('models')">Models</a>
      <a class="nav-item" onclick="showPage('dag')">DAG</a>
      <a class="nav-item" onclick="showPage('history')">Run History</a>
    </nav>
  </aside>

  <main id="main">
    <div id="topbar">
      <h2 id="page-title">Overview</h2>
      <button class="btn primary" onclick="triggerRun()">▶ kelpmesh run</button>
      <button class="btn" onclick="triggerPlan()">◎ kelpmesh plan</button>
      <button class="btn" onclick="loadData()">↺ Refresh</button>
    </div>
    <div id="content">
      <div id="page-overview"></div>
      <div id="page-models" style="display:none"></div>
      <div id="page-dag" style="display:none"></div>
      <div id="page-history" style="display:none"></div>
    </div>
  </main>

  <div id="toast"></div>

  <script>
    let _data = null;

    async function loadData() {
      try {
        const r = await fetch('/api/project');
        _data = await r.json();
        document.getElementById('proj-name').textContent = _data.name || 'kelpmesh project';
        renderCurrent();
      } catch(e) {
        showToast('Failed to load project data', true);
      }
    }

    function showPage(name) {
      ['overview','models','dag','history'].forEach(p => {
        document.getElementById('page-'+p).style.display = (p === name ? '' : 'none');
      });
      document.querySelectorAll('.nav-item').forEach((el, i) => {
        el.classList.toggle('active', ['overview','models','dag','history'][i] === name);
      });
      const titles = {overview:'Overview', models:'Models', dag:'Lineage DAG', history:'Run History'};
      document.getElementById('page-title').textContent = titles[name];
      _currentPage = name;
      renderCurrent();
    }

    let _currentPage = 'overview';
    function renderCurrent() {
      if (!_data) return;
      if (_currentPage === 'overview') renderOverview();
      else if (_currentPage === 'models') renderModels();
      else if (_currentPage === 'dag') renderDag();
      else if (_currentPage === 'history') renderHistory();
    }

    function renderOverview() {
      const models = _data.models || [];
      const history = _data.history || [];
      const types = {};
      models.forEach(m => { types[m.materialized] = (types[m.materialized]||0)+1; });
      const success = history.filter(r => r.status === 'success').length;
      const failed = history.filter(r => r.status === 'failed').length;
      document.getElementById('page-overview').innerHTML = `
        <div class="stat-row">
          <div class="stat"><div class="stat-val">${models.length}</div><div class="stat-label">Models</div></div>
          <div class="stat"><div class="stat-val">${types.incremental||0}</div><div class="stat-label">Incremental</div></div>
          <div class="stat"><div class="stat-val" style="color:var(--green)">${success}</div><div class="stat-label">Successful runs</div></div>
          <div class="stat"><div class="stat-val" style="color:var(--red)">${failed}</div><div class="stat-label">Failed runs</div></div>
        </div>
        <div class="card">
          <h3>Recent Activity</h3>
          ${history.slice(0,8).map(r => `
            <div class="run-row">
              <div class="status-dot ${r.status}"></div>
              <div class="run-name">${r.model_name}</div>
              <div class="run-time">${r.status} · ${r.elapsed ? r.elapsed.toFixed(2)+'s' : ''}</div>
            </div>
          `).join('') || '<div class="empty">No runs yet — click ▶ kelpmesh run to start</div>'}
        </div>`;
    }

    function renderModels() {
      const models = _data.models || [];
      document.getElementById('page-models').innerHTML = `
        <div class="model-grid">
          ${models.map(m => `
            <div class="model-card">
              <div class="model-name">${m.name}</div>
              <div class="model-type"><span class="tag ${m.materialized}">${m.materialized}</span></div>
            </div>
          `).join('')}
        </div>`;
    }

    function renderDag() {
      const models = _data.models || [];
      const el = document.getElementById('page-dag');
      el.innerHTML = '<div id="dag-container"><svg id="dag-svg" width="100%" height="400"></svg></div>';
      const svg = document.getElementById('dag-svg');
      const W = svg.clientWidth || 700, H = 400;
      if (!models.length) { svg.innerHTML = '<text x="50%" y="50%" text-anchor="middle">No models</text>'; return; }

      // Simple left-to-right layout: topological layers
      const deps = {};
      models.forEach(m => { deps[m.name] = m.upstream || []; });
      const layer = {};
      const assign = (name, visited = new Set()) => {
        if (name in layer) return layer[name];
        if (visited.has(name)) return 0;
        visited.add(name);
        const d = deps[name] || [];
        layer[name] = d.length ? Math.max(...d.map(n => assign(n, visited))) + 1 : 0;
        return layer[name];
      };
      models.forEach(m => assign(m.name));
      const maxL = Math.max(...Object.values(layer), 0);
      const layerGroups = {};
      models.forEach(m => { const l = layer[m.name]||0; (layerGroups[l]||(layerGroups[l]=[])).push(m.name); });

      const nodePos = {};
      const NW = 120, NH = 36, padX = 60, padY = 20;
      Object.entries(layerGroups).forEach(([l, names]) => {
        const x = 30 + parseInt(l) * (NW + padX);
        names.forEach((name, i) => {
          const totalH = names.length * (NH + padY) - padY;
          const startY = (H - totalH) / 2;
          nodePos[name] = { x, y: startY + i * (NH + padY) };
        });
      });

      const COLORS = { view: '#1e3a5f', table: '#1a3a1a', incremental: '#3a2a00', analysis: '#252525' };
      const STROKE = { view: '#5b8dee', table: '#4ade80', incremental: '#fbbf24', analysis: '#555' };

      let svgHtml = '';
      // Edges
      models.forEach(m => {
        (m.upstream||[]).forEach(up => {
          if (nodePos[up] && nodePos[m.name]) {
            const s = nodePos[up], t = nodePos[m.name];
            const x1 = s.x + NW, y1 = s.y + NH/2, x2 = t.x, y2 = t.y + NH/2;
            const cx = (x1+x2)/2;
            svgHtml += `<path d="M${x1},${y1} C${cx},${y1} ${cx},${y2} ${x2},${y2}" fill="none" stroke="#333" stroke-width="1.5"/>`;
          }
        });
      });
      // Nodes
      models.forEach(m => {
        if (!nodePos[m.name]) return;
        const {x, y} = nodePos[m.name];
        const mat = m.materialized || 'view';
        svgHtml += `<rect x="${x}" y="${y}" width="${NW}" height="${NH}" rx="5" fill="${COLORS[mat]||'#252525'}" stroke="${STROKE[mat]||'#555'}" stroke-width="1"/>`;
        svgHtml += `<text x="${x+NW/2}" y="${y+NH/2+4}" text-anchor="middle" font-size="11" fill="#e8e8e8">${m.name}</text>`;
      });
      svg.innerHTML = svgHtml;
    }

    function renderHistory() {
      const history = _data.history || [];
      document.getElementById('page-history').innerHTML = `
        <div class="card">
          <h3>All Runs</h3>
          ${history.map(r => `
            <div class="run-row">
              <div class="status-dot ${r.status}"></div>
              <div class="run-name">${r.model_name}</div>
              <div class="run-time">${r.status} · ${r.elapsed ? r.elapsed.toFixed(2)+'s' : '—'} · rows: ${r.row_count||0}</div>
            </div>
          `).join('') || '<div class="empty">No history yet</div>'}
        </div>`;
    }

    async function triggerRun() {
      showToast('Running kelpmesh run...');
      const r = await fetch('/api/run', {method:'POST'});
      const d = await r.json();
      showToast(d.ok ? `Done: ${d.success} succeeded, ${d.failed} failed` : 'Run failed: ' + d.error, !d.ok);
      loadData();
    }

    async function triggerPlan() {
      showToast('Running kelpmesh plan...');
      const r = await fetch('/api/plan', {method:'POST'});
      const d = await r.json();
      showToast('Plan complete — check terminal for output');
    }

    function showToast(msg, err=false) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.style.background = err ? '#dc2626' : 'var(--accent)';
      t.style.display = 'block';
      setTimeout(() => { t.style.display = 'none'; }, 3500);
    }

    loadData();
  </script>
</body>
</html>
"""


def create_app(project_dir: str = ".") -> FastAPI:
    """Create the kelpmesh Studio FastAPI application."""
    app = FastAPI(title="kelpmesh Studio", docs_url=None, redoc_url=None)
    _project_dir = Path(project_dir).resolve()

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return _HTML

    @app.get("/api/project")
    async def project_info():
        try:
            from kelpmesh.core.project import Project
            from kelpmesh.state.engine import StateEngine

            project = Project(_project_dir)
            state = StateEngine(_project_dir)

            models_data = []
            for name, model in project.models.items():
                models_data.append({
                    "name": name,
                    "materialized": model.materialized,
                    "upstream": list(model.upstream),
                    "tags": model.tags,
                    "enabled": model.enabled,
                })

            history = []
            try:
                from kelpmesh.observability.history import RunHistory
                rh = RunHistory(_project_dir)
                rows = rh.get_history(limit=100)
                history = [
                    {
                        "model_name": r.get("model_name", ""),
                        "status": r.get("status", ""),
                        "elapsed": r.get("elapsed_s"),
                        "row_count": r.get("row_count", 0),
                    }
                    for r in rows
                ]
                rh.close()
            except Exception:
                pass

            state.close()
            return {
                "name": project.config.name,
                "models": models_data,
                "history": history,
                "warehouse": project.config.warehouse.type,
            }
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/api/run")
    async def run_project():
        try:
            result = subprocess.run(
                [sys.executable, "-m", "kelpmesh", "run", "--project-dir", str(_project_dir)],
                capture_output=True,
                text=True,
                timeout=300,
            )
            lines = result.stdout.splitlines()
            ok_count = sum(1 for l in lines if "✓" in l or "success" in l.lower())
            err_count = sum(1 for l in lines if "✗" in l or "failed" in l.lower())
            return {"ok": result.returncode == 0, "success": ok_count, "failed": err_count, "output": result.stdout[-2000:]}
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.post("/api/plan")
    async def plan_project():
        try:
            result = subprocess.run(
                [sys.executable, "-m", "kelpmesh", "plan", "--project-dir", str(_project_dir)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {"ok": result.returncode == 0, "output": result.stdout}
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    return app
