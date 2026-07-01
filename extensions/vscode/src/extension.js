'use strict';
const vscode = require('vscode');
const path = require('path');
const cp = require('child_process');

// ── Globals ────────────────────────────────────────────────────────────────
let outputChannel;
let statusBarItem;
let modelTreeProvider;
let manifestCache = { models: [], generated_at: '', project: '' };

// ── Activation ─────────────────────────────────────────────────────────────
function activate(context) {
    outputChannel = vscode.window.createOutputChannel('KelpMesh');
    context.subscriptions.push(outputChannel);

    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.text = '$(database) KelpMesh';
    statusBarItem.tooltip = 'KelpMesh — click to show DAG';
    statusBarItem.command = 'kelpmesh.showDag';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Load manifest on activation
    refreshManifest();

    // Model tree view
    modelTreeProvider = new ModelTreeProvider();
    const treeView = vscode.window.createTreeView('kelpmeshModels', {
        treeDataProvider: modelTreeProvider,
        showCollapseAll: true,
    });
    context.subscriptions.push(treeView);

    // Commands
    const cmds = {
        'kelpmesh.runModel':      () => runModelCmd(),
        'kelpmesh.testModel':     () => testModelCmd(),
        'kelpmesh.buildModel':    () => buildModelCmd(),
        'kelpmesh.previewModel':  () => previewModelCmd(),
        'kelpmesh.compileModel':  () => compileModelCmd(),
        'kelpmesh.planProject':   () => planProjectCmd(),
        'kelpmesh.showLineage':   () => showLineageCmd(),
        'kelpmesh.showDag':       () => showDagCmd(),
        'kelpmesh.showModelDocs': () => showModelDocsCmd(),
        'kelpmesh.showModelSource': () => showModelSourceCmd(),
        'kelpmesh.runProject':    () => runProjectCmd(),
        'kelpmesh.scanProject':   () => scanProjectCmd(),
        'kelpmesh.openStudio':    () => openStudioCmd(),
        'kelpmesh.refreshModels': () => { refreshManifest(); modelTreeProvider.refresh(); updateStatusBar(); },
    };
    for (const [cmd, fn] of Object.entries(cmds)) {
        context.subscriptions.push(vscode.commands.registerCommand(cmd, fn));
    }

    // Code lens
    if (vscode.workspace.getConfiguration('kelpmesh').get('showCodeLens', true)) {
        context.subscriptions.push(
            vscode.languages.registerCodeLensProvider(
                [{ language: 'sql', scheme: 'file' }, { language: 'python', scheme: 'file' }],
                new KelpMeshCodeLensProvider()
            )
        );
    }

    // Auto-run on save
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument(doc => {
            const cfg = vscode.workspace.getConfiguration('kelpmesh');
            if (!cfg.get('autoRunOnSave', false)) return;
            if (!isModelFile(doc)) return;
            runModelCmd(doc);
        })
    );

    // Diagnostics on open/change
    const diagCollection = vscode.languages.createDiagnosticCollection('kelpmesh');
    context.subscriptions.push(diagCollection);
    context.subscriptions.push(
        vscode.workspace.onDidOpenTextDocument(doc => {
            if (doc.languageId === 'sql') lintModel(doc, diagCollection);
        })
    );
    context.subscriptions.push(
        vscode.workspace.onDidChangeTextDocument(e => {
            if (e.document.languageId === 'sql') lintModel(e.document, diagCollection);
        })
    );
}

function deactivate() {}

// ── Helpers ────────────────────────────────────────────────────────────────
function getPython() {
    const cfg = vscode.workspace.getConfiguration('kelpmesh');
    const custom = cfg.get('pythonPath', '').trim();
    if (custom) return custom;
    const pythonExt = vscode.extensions.getExtension('ms-python.python');
    if (pythonExt?.isActive) {
        const interp = pythonExt.exports?.settings?.getExecutionDetails?.()?.execCommand;
        if (interp?.[0]) return interp[0];
    }
    return 'python';
}

function getProjectDir() {
    const cfg = vscode.workspace.getConfiguration('kelpmesh');
    const custom = cfg.get('projectDir', '').trim();
    if (custom) return custom;
    const folders = vscode.workspace.workspaceFolders;
    if (!folders?.length) { vscode.window.showErrorMessage('KelpMesh: No workspace folder open.'); return null; }
    return folders[0].uri.fsPath;
}

function modelNameFrom(doc) {
    return path.basename(doc.fileName).replace(/\.(sql|py)$/, '');
}

function isModelFile(doc) {
    return /\.(sql|py)$/.test(doc.fileName) &&
        doc.uri.fsPath.includes(path.sep + 'models' + path.sep);
}

function setStatus(text, tooltip) {
    statusBarItem.text = `$(database) KelpMesh${text ? ' ' + text : ''}`;
    statusBarItem.tooltip = tooltip || text || 'KelpMesh — click to show DAG';
}

function updateStatusBar() {
    const count = manifestCache.models.length;
    setStatus(`$(list-tree) ${count}`, `${count} models — click to show DAG`);
}

function refreshManifest() {
    const python = getPython();
    const projectDir = getProjectDir();
    if (!projectDir) return;
    try {
        const out = cp.execSync(
            `"${python}" -m kelpmesh docs manifest`,
            { cwd: projectDir, encoding: 'utf8', timeout: 30000 }
        );
        manifestCache = JSON.parse(out);
    } catch (_) {
        manifestCache = { models: [], generated_at: '', project: '' };
    }
    updateStatusBar();
}

function getManifestModel(name) {
    return manifestCache.models.find(m => m.name === name);
}

// ── Async command runner (streaming to output channel) ────────────────────
function runKM(args, { title, onSuccess, onFail } = {}) {
    const python = getPython();
    const projectDir = getProjectDir();
    if (!projectDir) return;

    outputChannel.show(true);
    outputChannel.appendLine(`\n${'─'.repeat(60)}`);
    outputChannel.appendLine(`▶  kelpmesh ${args.join(' ')}`);
    outputChannel.appendLine(`${'─'.repeat(60)}`);

    setStatus('$(sync~spin) running…', title || args.join(' '));

    return new Promise(resolve => {
        const child = cp.spawn(python, ['-m', 'kelpmesh', ...args], {
            cwd: projectDir,
            env: { ...process.env, PYTHONUNBUFFERED: '1' },
        });

        child.stdout.on('data', d => outputChannel.append(d.toString()));
        child.stderr.on('data', d => outputChannel.append(d.toString()));

        child.on('close', code => {
            if (code === 0) {
                setStatus('$(check) done');
                if (onSuccess) onSuccess();
                else vscode.window.showInformationMessage(`KelpMesh: ${title || args[0]} succeeded ✓`);
            } else {
                setStatus('$(error) failed');
                if (onFail) onFail(code);
                else vscode.window.showErrorMessage(`KelpMesh: ${title || args[0]} failed (rc=${code}) — see Output panel`);
            }
            setTimeout(() => updateStatusBar(), 4000);
            modelTreeProvider.refresh();
            resolve(code);
        });

        child.on('error', err => {
            outputChannel.appendLine(`[error] ${err.message}`);
            vscode.window.showErrorMessage(
                `KelpMesh: Cannot start Python (${python}). ` +
                `Check 'kelpmesh.pythonPath' in Settings — run 'which python' or 'where python' to find the right path.`
            );
            setStatus('');
            resolve(1);
        });
    });
}

// ── Webview message handlers ───────────────────────────────────────────────
function setupWebviewMessageListener(panel) {
    panel.webview.onDidReceiveMessage(msg => {
        if (msg.command === 'openFile' && msg.path) {
            const projectDir = getProjectDir();
            if (!projectDir) return;
            const fullPath = path.isAbsolute(msg.path) ? msg.path : path.join(projectDir, msg.path);
            vscode.workspace.openTextDocument(fullPath).then(doc => {
                vscode.window.showTextDocument(doc);
            }, () => {
                vscode.window.showErrorMessage(`KelpMesh: Cannot open ${msg.path}`);
            });
        }
    });
}

// ── Commands ───────────────────────────────────────────────────────────────
async function runModelCmd(doc) {
    const editor = doc ? { document: doc } : vscode.window.activeTextEditor;
    if (!editor) return;
    const name = modelNameFrom(editor.document);
    await runKM(['run', '--select', name], { title: `run ${name}` });
}

async function testModelCmd() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;
    const name = modelNameFrom(editor.document);
    await runKM(['test', '--select', name], { title: `test ${name}` });
}

async function buildModelCmd() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;
    const name = modelNameFrom(editor.document);
    await runKM(['build', '--select', name], { title: `build ${name}` });
}

async function previewModelCmd() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;
    const name = modelNameFrom(editor.document);
    const python = getPython();
    const projectDir = getProjectDir();
    if (!projectDir) return;

    try {
        const out = cp.execSync(
            `"${python}" -m kelpmesh preview --select ${name}`,
            { cwd: projectDir, encoding: 'utf8', timeout: 30000 }
        );
        const panel = vscode.window.createWebviewPanel(
            'kelpmeshPreview', `Preview: ${name}`, vscode.ViewColumn.Beside,
            { enableScripts: false }
        );
        panel.webview.html = buildPreviewHtml(name, out);
    } catch (e) {
        vscode.window.showErrorMessage(`KelpMesh: Preview failed — ${e.message}`);
    }
}

async function compileModelCmd() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;
    const name = modelNameFrom(editor.document);
    const python = getPython();
    const projectDir = getProjectDir();
    if (!projectDir) return;

    try {
        const out = cp.execSync(
            `"${python}" -m kelpmesh compile --select ${name} --print`,
            { cwd: projectDir, encoding: 'utf8', timeout: 20000 }
        );
        const doc = await vscode.workspace.openTextDocument({ content: out, language: 'sql' });
        await vscode.window.showTextDocument(doc, vscode.ViewColumn.Beside);
    } catch (e) {
        vscode.window.showErrorMessage(`KelpMesh: Compile failed — ${e.message}`);
    }
}

async function showModelDocsCmd() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;
    const name = modelNameFrom(editor.document);
    const model = getManifestModel(name);
    if (!model || !model.description) {
        vscode.window.showInformationMessage(`KelpMesh: No documentation for ${name}`);
        return;
    }
    const panel = vscode.window.createWebviewPanel(
        'kelpmeshDocs', `Docs: ${name}`, vscode.ViewColumn.Beside,
        { enableScripts: false }
    );
    const cols = (model.columns || []).map(c => `
        <tr><td><code>${c.name}</code></td><td>${c.data_type || '—'}</td><td>${c.description || '—'}</td></tr>
    `).join('');
    panel.webview.html = `<!DOCTYPE html><html><head><style>${vsStyles()}</style></head><body>
        <h2>${name}</h2>
        <p style="color:var(--vscode-descriptionForeground)">${model.description || 'No description'}</p>
        ${model.tags?.length ? `<p>Tags: ${model.tags.map(t => `<span class="dep-chip">${t}</span>`).join(' ')}</p>` : ''}
        <h3>Columns (${model.columns?.length || 0})</h3>
        <table><thead><tr><th>Name</th><th>Type</th><th>Description</th></tr></thead>
        <tbody>${cols || '<tr><td colspan="3" style="color:var(--vscode-descriptionForeground)">No column metadata</td></tr>'}</tbody></table>
        </body></html>`;
}

async function showModelSourceCmd() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;
    const name = modelNameFrom(editor.document);
    const model = getManifestModel(name);
    if (!model || !model.sql) {
        vscode.window.showInformationMessage(`KelpMesh: No source available for ${name}`);
        return;
    }
    const doc = await vscode.workspace.openTextDocument({ content: model.sql, language: 'sql' });
    await vscode.window.showTextDocument(doc, vscode.ViewColumn.Beside);
}

async function planProjectCmd() {
    const python = getPython();
    const projectDir = getProjectDir();
    if (!projectDir) return;

    outputChannel.show(true);
    outputChannel.appendLine('\n' + '─'.repeat(60));
    outputChannel.appendLine('▶  kelpmesh plan');
    outputChannel.appendLine('─'.repeat(60));
    setStatus('$(sync~spin) planning…');

    try {
        const out = cp.execSync(
            `"${python}" -m kelpmesh plan`,
            { cwd: projectDir, encoding: 'utf8', timeout: 60000 }
        );
        outputChannel.append(out);

        const panel = vscode.window.createWebviewPanel(
            'kelpmeshPlan', 'KelpMesh Plan', vscode.ViewColumn.Beside,
            { enableScripts: false }
        );
        panel.webview.html = buildPlanHtml(out);
        setStatus('$(check) plan done');
    } catch (e) {
        outputChannel.appendLine(e.stderr || e.message);
        vscode.window.showErrorMessage('KelpMesh: Plan failed — see Output panel');
        setStatus('$(error) plan failed');
    }
    setTimeout(() => updateStatusBar(), 4000);
}

async function showLineageCmd() {
    const python = getPython();
    const projectDir = getProjectDir();
    if (!projectDir) return;

    const editor = vscode.window.activeTextEditor;
    const activeModel = editor ? modelNameFrom(editor.document) : '';

    // Refresh manifest if empty
    if (!manifestCache.models.length) refreshManifest();

    const panel = vscode.window.createWebviewPanel(
        'kelpmeshLineage', 'KelpMesh Lineage', vscode.ViewColumn.Beside,
        { enableScripts: true }
    );
    setupWebviewMessageListener(panel);
    panel.webview.html = buildLineageHtml(manifestCache.models || [], activeModel);
}

async function showDagCmd() {
    const projectDir = getProjectDir();
    if (!projectDir) return;

    if (!manifestCache.models.length) refreshManifest();

    const panel = vscode.window.createWebviewPanel(
        'kelpmeshDag', 'KelpMesh DAG', vscode.ViewColumn.Beside,
        { enableScripts: true }
    );
    setupWebviewMessageListener(panel);
    panel.webview.html = buildDagHtml(manifestCache.models || []);
}

async function runProjectCmd() {
    await runKM(['run'], { title: 'run all models' });
    refreshManifest();
}

async function scanProjectCmd() {
    await runKM(['scan', 'pii'], { title: 'scan for PII' });
}

async function openStudioCmd() {
    const python = getPython();
    const projectDir = getProjectDir();
    if (!projectDir) return;

    const child = cp.spawn(python, ['-m', 'kelpmesh_studio'], {
        cwd: projectDir,
        detached: true,
        stdio: 'ignore',
    });
    child.unref();

    setTimeout(() => {
        vscode.env.openExternal(vscode.Uri.parse('http://localhost:8765'));
    }, 2000);

    vscode.window.showInformationMessage(
        'KelpMesh Studio starting at http://localhost:8765…',
        'Open Browser'
    ).then(sel => {
        if (sel === 'Open Browser') vscode.env.openExternal(vscode.Uri.parse('http://localhost:8501'));
    });
}

// ── Diagnostics (basic linting) ────────────────────────────────────────────
function lintModel(doc, collection) {
    const text = doc.getText();
    const diags = [];
    const lines = text.split('\n');

    const secretRe = /(?:password|secret|token|key)\s*=\s*['"][^'"]{6,}['"]/i;
    lines.forEach((line, i) => {
        if (secretRe.test(line)) {
            diags.push(new vscode.Diagnostic(
                new vscode.Range(i, 0, i, line.length),
                'KelpMesh: Possible hardcoded credential — use {{ env_var("NAME") }} instead',
                vscode.DiagnosticSeverity.Warning
            ));
        }
    });

    lines.forEach((line, i) => {
        if (line.includes('{{ ref(') && !line.includes('}}')) {
            diags.push(new vscode.Diagnostic(
                new vscode.Range(i, 0, i, line.length),
                'KelpMesh: Unclosed {{ ref() }} — missing }}',
                vscode.DiagnosticSeverity.Error
            ));
        }
    });

    collection.set(doc.uri, diags);
}

// ── Code Lens ──────────────────────────────────────────────────────────────
class KelpMeshCodeLensProvider {
    provideCodeLenses(doc) {
        if (!isModelFile(doc) && !/\.(sql|py)$/.test(doc.fileName)) return [];
        const name = modelNameFrom(doc);
        const top = new vscode.Range(0, 0, 0, 0);
        const lenses = [
            new vscode.CodeLens(top, { title: '$(play) Run',     command: 'kelpmesh.runModel' }),
            new vscode.CodeLens(top, { title: '$(beaker) Test',  command: 'kelpmesh.testModel' }),
            new vscode.CodeLens(top, { title: '$(rocket) Build', command: 'kelpmesh.buildModel' }),
            new vscode.CodeLens(top, { title: '$(eye) Preview',  command: 'kelpmesh.previewModel' }),
            new vscode.CodeLens(top, { title: '$(code) Compile', command: 'kelpmesh.compileModel' }),
            new vscode.CodeLens(top, { title: '$(book) Docs',    command: 'kelpmesh.showModelDocs' }),
            new vscode.CodeLens(top, { title: '$(type-hierarchy) Lineage', command: 'kelpmesh.showLineage' }),
        ];
        return lenses;
    }
}

// ── Model Tree View ────────────────────────────────────────────────────────
const MAT_ORDER = ['view', 'table', 'incremental', 'snapshot', 'python', 'other'];
const MAT_LABELS = { view:'Views', table:'Tables', incremental:'Incremental', snapshot:'Snapshots', python:'Python Models', other:'Other' };
const MAT_ICONS = { view:'$(symbol-file)', table:'$(database)', incremental:'$(sync)', snapshot:'$(camera)', python:'$(symbol-method)', other:'$(question)' };
const MAT_STATUS_COLORS = { view:'#a6e3a1', table:'#89b4fa', incremental:'#f9e2af', snapshot:'#cba6f7', python:'#94e2d5' };

class ModelTreeProvider {
    constructor() {
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    }
    refresh() { this._onDidChangeTreeData.fire(); }

    getTreeItem(element) {
        if (element.isGroup) {
            const item = new vscode.TreeItem(element.label, vscode.TreeItemCollapsibleState.Collapsed);
            item.iconPath = new vscode.ThemeIcon(element.iconId || 'list-tree');
            item.contextValue = 'modelGroup';
            item.description = `(${element.count})`;
            item.tooltip = `${element.label} — ${element.count} models`;
            return item;
        }
        const item = new vscode.TreeItem(element.label, vscode.TreeItemCollapsibleState.None);
        item.description = element.materialized || '';
        const m = getManifestModel(element.label);
        if (m?.description) item.tooltip = `${element.label} (${element.materialized})\n${m.description}`;
        else item.tooltip = `${element.label} (${element.materialized})`;
        item.command = { command: 'vscode.open', title: 'Open', arguments: [element.uri] };
        item.iconPath = new vscode.ThemeIcon(element.type === 'python' ? 'symbol-method' : 'symbol-file');
        item.contextValue = 'modelItem';
        return item;
    }

    async getChildren(element) {
        const projectDir = getProjectDir();
        if (!projectDir) return [];

        // If element is a group, return its models
        if (element?.isGroup) return element.children || [];

        // Root level: return groups
        const modelsDir = path.join(projectDir, 'models');
        try {
            const { readdirSync, statSync } = require('fs');
            const files = readdirSync(modelsDir, { recursive: true })
                .filter(f => /\.(sql|py)$/.test(f))
                .map(f => {
                    const fullPath = path.join(modelsDir, f);
                    const label = path.basename(f).replace(/\.(sql|py)$/, '');
                    const type = f.endsWith('.py') ? 'python' : 'sql';
                    const m = getManifestModel(label);
                    return { label, uri: vscode.Uri.file(fullPath), type, materialized: m?.materialized || type };
                });

            // Group by materialization
            const groups = {};
            files.forEach(f => {
                const mat = f.materialized;
                const key = MAT_ORDER.includes(mat) ? mat : 'other';
                if (!groups[key]) groups[key] = [];
                groups[key].push(f);
            });

            return MAT_ORDER
                .filter(k => groups[k]?.length)
                .map(k => ({
                    isGroup: true,
                    label: MAT_LABELS[k] || k,
                    iconId: k,
                    count: groups[k].length,
                    children: groups[k],
                }));
        } catch (_) { return []; }
    }
}

// ── HTML builders ──────────────────────────────────────────────────────────
function vsStyles() {
    return `
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:13px;padding:16px;background:var(--vscode-editor-background);color:var(--vscode-editor-foreground)}
        h2{font-size:1.1rem;margin-bottom:12px;font-weight:600}
        h3{font-size:0.95rem;margin:12px 0 8px;font-weight:600;color:var(--vscode-descriptionForeground)}
        .badge{display:inline-block;padding:1px 7px;border-radius:3px;font-size:11px;background:var(--vscode-badge-background);color:var(--vscode-badge-foreground);margin-left:6px}
        pre{white-space:pre-wrap;word-break:break-word;background:var(--vscode-textBlockQuote-background);padding:10px;border-radius:4px;font-family:var(--vscode-editor-font-family,'Courier New'),monospace;font-size:12px}
        table{border-collapse:collapse;width:100%;font-size:12px}
        th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--vscode-widget-border)}
        th{font-weight:600;background:var(--vscode-sideBar-background)}
        .model-card{background:var(--vscode-sideBar-background);border:1px solid var(--vscode-widget-border);border-radius:5px;padding:10px;margin-bottom:8px}
        .model-card.active{border-color:var(--vscode-focusBorder)}
        .dep-label{font-size:11px;color:var(--vscode-descriptionForeground);margin-top:6px}
        .dep-list{display:flex;flex-wrap:wrap;gap:4px;margin-top:3px}
        .dep-chip{font-size:11px;padding:1px 7px;border-radius:3px;background:var(--vscode-badge-background);color:var(--vscode-badge-foreground)}
        .warn{color:var(--vscode-editorWarning-foreground)}
        .ok{color:var(--vscode-testing-iconPassed)}
        .toggle-bar{display:flex;gap:6px;margin-bottom:12px}
        .toggle-btn{padding:4px 12px;font-size:12px;border:1px solid var(--vscode-widget-border);background:var(--vscode-sideBar-background);color:var(--vscode-editor-foreground);cursor:pointer;border-radius:4px}
        .toggle-btn.active{background:var(--vscode-button-background);color:var(--vscode-button-foreground);border-color:var(--vscode-button-background)}
        .dag-wrap{background:var(--vscode-editor-background);border:1px solid var(--vscode-widget-border);border-radius:6px;overflow:hidden;position:relative}
        .dag-wrap svg{display:block;width:100%;height:auto;min-height:300px}
        .dag-legend{display:flex;gap:12px;padding:8px 12px;flex-wrap:wrap;font-size:10px}
        .dag-legend-item{display:flex;align-items:center;gap:4px}
        .dag-legend-dot{width:8px;height:8px;border-radius:2px}
        .dag-node{cursor:pointer}
        .dag-node rect{transition:stroke-width 0.15s,opacity 0.15s}
        .dag-node:hover rect{stroke-width:2}
        .search-bar{width:100%;padding:6px 10px;margin-bottom:10px;border:1px solid var(--vscode-widget-border);border-radius:4px;background:var(--vscode-input-background);color:var(--vscode-input-foreground);font-size:12px;box-sizing:border-box}
        .search-bar:focus{outline:1px solid var(--vscode-focusBorder)}
    `;
}

function buildPreviewHtml(name, raw) {
    const lines = raw.split('\n').filter(l => l.trim() && !l.startsWith('-'));
    let tableHtml = '';
    if (lines.length > 0) {
        const header = lines[0].split('|').map(c => c.trim()).filter(Boolean);
        const rows = lines.slice(1).map(l => l.split('|').map(c => c.trim()).filter(Boolean));
        tableHtml = `<table><thead><tr>${header.map(h => `<th>${h}</th>`).join('')}</tr></thead>
            <tbody>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
    } else {
        tableHtml = `<pre>${raw}</pre>`;
    }
    return `<!DOCTYPE html><html><head><style>${vsStyles()}</style></head><body>
        <h2>Preview: ${name}</h2>${tableHtml}</body></html>`;
}

function buildPlanHtml(raw) {
    return `<!DOCTYPE html><html><head><style>${vsStyles()}</style></head><body>
        <h2>$(graph-line) KelpMesh Plan</h2>
        <pre>${raw.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</pre>
        </body></html>`;
}

// ── DAG webview (interactive SVG) ─────────────────────────────────────────
function buildDagHtml(models) {
    const modelJson = JSON.stringify(models);
    return `<!DOCTYPE html><html><head><style>${vsStyles()}</style>
    <style>
        body{padding:12px}
        .toolbar{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
        .toolbar h2{margin:0;font-size:1rem}
        .filter-input{padding:4px 8px;border:1px solid var(--vscode-widget-border);border-radius:4px;background:var(--vscode-input-background);color:var(--vscode-input-foreground);font-size:12px;flex:1;max-width:240px}
    </style>
    </head><body>
    <div class="toolbar">
        <h2>KelpMesh DAG</h2>
        <input class="filter-input" id="filter" placeholder="Filter models..." oninput="renderDag()">
        <span style="font-size:11px;color:var(--vscode-descriptionForeground)" id="count"></span>
    </div>
    <div id="legend"></div>
    <div id="dag" class="dag-wrap"></div>
    <script>
    const models = ${modelJson};
    const COL = { view:'#a6e3a1', table:'#89b4fa', incremental:'#f9e2af', snapshot:'#cba6f7', python:'#94e2d5', analysis:'#6c7086' };

    function renderDag() {
        const filter = (document.getElementById('filter').value || '').toLowerCase();
        const filtered = filter ? models.filter(m => m.name.toLowerCase().includes(filter)) : models;
        document.getElementById('count').textContent = filtered.length + '/' + models.length + ' models';

        if (!filtered.length) {
            document.getElementById('dag').innerHTML = '<div style="padding:40px;text-align:center;color:var(--vscode-descriptionForeground)">No models match filter</div>';
            document.getElementById('legend').innerHTML = '';
            return;
        }

        // Layer assignment (topological sort)
        const deps = {};
        filtered.forEach(m => { deps[m.name] = (m.upstream||[]).filter(u => filtered.some(f => f.name === u)); });
        const layer = {}, visited = new Set();
        function assign(name) {
            if (name in layer) return layer[name];
            if (visited.has(name)) return 0;
            visited.add(name);
            const d = deps[name] || [];
            layer[name] = d.length ? Math.max(...d.map(n => assign(n))) + 1 : 0;
            return layer[name];
        }
        filtered.forEach(m => assign(m.name));
        const maxL = Math.max(...Object.values(layer), 0);
        const groups = {};
        filtered.forEach(m => { const l = layer[m.name]||0; (groups[l]||(groups[l]=[])).push(m.name); });

        const NW = 130, NH = 34, padX = 50, padY = 24;
        const W = Math.max(600, (maxL+1) * (NW + padX) + 40);
        let maxInLayer = Math.max(...Object.values(groups).map(g => g.length), 1);
        const H = Math.max(300, maxInLayer * (NH + padY) + 40);
        const pos = {};
        Object.entries(groups).forEach(([l, names]) => {
            const x = 20 + parseInt(l) * (NW + padX);
            names.forEach((name, i) => {
                const totalH = names.length * (NH + padY) - padY;
                pos[name] = { x, y: (H - totalH) / 2 + i * (NH + padY) };
            });
        });

        let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '"><defs><marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5"><path d="M0,0 L8,4 L0,8" fill="var(--vscode-widget-border)"/></marker></defs>';

        // Edges
        filtered.forEach(m => {
            (m.upstream||[]).forEach(up => {
                if (pos[up] && pos[m.name]) {
                    const s = pos[up], t = pos[m.name];
                    const x1 = s.x+NW, y1 = s.y+NH/2, x2 = t.x, y2 = t.y+NH/2, cx = (x1+x2)/2;
                    svg += '<path d="M' + x1 + ',' + y1 + ' C' + cx + ',' + y1 + ' ' + cx + ',' + y2 + ' ' + (x2-1) + ',' + y2 + '" fill="none" stroke="var(--vscode-widget-border)" stroke-width="1.5" marker-end="url(#arrow)"/>';
                }
            });
        });

        // Nodes
        filtered.forEach(m => {
            if (!pos[m.name]) return;
            const {x,y} = pos[m.name];
            const c = COL[m.materialized] || '#6c7086';
            const label = m.name.length > 16 ? m.name.slice(0,15) + '\u2026' : m.name;
            svg += '<g class="dag-node" onclick="openModel(\'' + m.name + '\')" onmouseover="this.querySelector(\'rect\').style.opacity=0.85" onmouseout="this.querySelector(\'rect\').style.opacity=1">';
            svg += '<rect x="' + x + '" y="' + y + '" width="' + NW + '" height="' + NH + '" rx="5" fill="var(--vscode-sideBar-background)" stroke="' + c + '" stroke-width="1"/>';
            svg += '<text x="' + (x+NW/2) + '" y="' + (y+NH/2+4) + '" text-anchor="middle" font-size="11" font-family="var(--vscode-editor-font-family)" fill="' + c + '" font-weight="500">' + label + '</text>';
            svg += '</g>';
        });
        svg += '</svg>';

        document.getElementById('legend').innerHTML = '<div class="dag-legend">' + Object.entries(COL).map(([k,v]) => '<div class="dag-legend-item"><div class="dag-legend-dot" style="background:' + v + '"></div>' + k + '</div>').join('') + '</div>';
        document.getElementById('dag').innerHTML = svg;
    }

    function openModel(name) {
        const m = models.find(x => x.name === name);
        if (m && m.path) {
            acquireVsCodeApi().postMessage({ command: 'openFile', path: m.path });
        }
    }
    renderDag();
    </script>
    </body></html>`;
}

// ── Lineage webview (card list + DAG toggle) ──────────────────────────────
function buildLineageHtml(models, activeModel) {
    const modelJson = JSON.stringify(models);
    const active = JSON.stringify(activeModel);
    return `<!DOCTYPE html><html><head><style>${vsStyles()}</style>
    <style>
        body{padding:12px}
        .toolbar{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
        .toolbar h2{margin:0;font-size:1rem}
        .mode-bar{display:flex;gap:4px;margin-left:auto}
        .mode-btn{padding:3px 10px;font-size:11px;border:1px solid var(--vscode-widget-border);background:var(--vscode-sideBar-background);color:var(--vscode-editor-foreground);cursor:pointer;border-radius:3px}
        .mode-btn.active{background:var(--vscode-button-background);color:var(--vscode-button-foreground);border-color:var(--vscode-button-background)}
        .dag-wrap{background:var(--vscode-editor-background);border:1px solid var(--vscode-widget-border);border-radius:6px;overflow:hidden}
        .dag-wrap svg{display:block;width:100%;height:auto;min-height:300px}
        .dag-legend{display:flex;gap:12px;padding:8px 12px;flex-wrap:wrap;font-size:10px}
        .dag-legend-item{display:flex;align-items:center;gap:4px}
        .dag-legend-dot{width:8px;height:8px;border-radius:2px}
        .dag-node{cursor:pointer}
    </style>
    </head><body>
    <div class="toolbar">
        <h2>KelpMesh Lineage</h2>
        <div class="mode-bar">
            <button class="mode-btn active" id="btn-cards" onclick="setMode('cards')">Cards</button>
            <button class="mode-btn" id="btn-dag" onclick="setMode('dag')">DAG</button>
            <button class="mode-btn" id="btn-both" onclick="setMode('both')">Both</button>
        </div>
    </div>
    <div id="content"></div>
    <div id="dag" style="display:none" class="dag-wrap"></div>

    <script>
    const models = ${modelJson};
    const activeModel = ${active};
    const COL = { view:'#a6e3a1', table:'#89b4fa', incremental:'#f9e2af', snapshot:'#cba6f7', python:'#94e2d5', analysis:'#6c7086' };
    let currentMode = 'cards';

    // Get VS Code API
    const vscodeApi = acquireVsCodeApi();

    function renderCards() {
        const cards = models.map(m => {
            const isActive = m.name === activeModel;
            const up = (m.upstream || []).map(u => '<span class="dep-chip">' + u + '</span>').join('');
            const dn = (m.downstream || []).map(d => '<span class="dep-chip">' + d + '</span>').join('');
            return '<div class="model-card' + (isActive ? ' active' : '') + '" onclick="openModel(\'' + m.name + '\')" style="cursor:pointer">' +
                '<strong>' + m.name + '</strong><span class="badge">' + (m.materialized || 'view') + '</span>' +
                (m.description ? '<br><span style="font-size:11px;color:var(--vscode-descriptionForeground)">' + m.description.slice(0,80) + '</span>' : '') +
                (up ? '<div class="dep-label">Upstream</div><div class="dep-list">' + up + '</div>' : '') +
                (dn ? '<div class="dep-label">Downstream</div><div class="dep-list">' + dn + '</div>' : '') +
            '</div>';
        }).join('');
        document.getElementById('content').innerHTML = cards || '<p style="color:var(--vscode-descriptionForeground)">No models found.</p>';
    }

    function renderDag() {
        if (!models.length) { document.getElementById('dag').innerHTML = '<div style="padding:40px;text-align:center;color:var(--vscode-descriptionForeground)">No models</div>'; return; }
        const deps = {};
        models.forEach(m => { deps[m.name] = m.upstream || []; });
        const layer = {}, visited = new Set();
        function assign(name) {
            if (name in layer) return layer[name];
            if (visited.has(name)) return 0;
            visited.add(name);
            const d = deps[name] || [];
            layer[name] = d.length ? Math.max(...d.map(n => assign(n))) + 1 : 0;
            return layer[name];
        }
        models.forEach(m => assign(m.name));
        const maxL = Math.max(...Object.values(layer), 0);
        const groups = {};
        models.forEach(m => { const l = layer[m.name]||0; (groups[l]||(groups[l]=[])).push(m.name); });

        const NW = 120, NH = 32, padX = 40, padY = 20;
        const W = Math.max(500, (maxL+1) * (NW + padX) + 30);
        let maxInLayer = Math.max(...Object.values(groups).map(g => g.length), 1);
        const H = Math.max(250, maxInLayer * (NH + padY) + 30);
        const pos = {};
        Object.entries(groups).forEach(([l, names]) => {
            const x = 15 + parseInt(l) * (NW + padX);
            names.forEach((name, i) => {
                const totalH = names.length * (NH + padY) - padY;
                pos[name] = { x, y: (H - totalH) / 2 + i * (NH + padY) };
            });
        });

        let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '"><defs><marker id="arrow2" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="4" markerHeight="4"><path d="M0,0 L8,4 L0,8" fill="var(--vscode-widget-border)"/></marker></defs>';

        models.forEach(m => {
            (m.upstream||[]).forEach(up => {
                if (pos[up] && pos[m.name]) {
                    const s = pos[up], t = pos[m.name];
                    const x1 = s.x+NW, y1 = s.y+NH/2, x2 = t.x, y2 = t.y+NH/2, cx = (x1+x2)/2;
                    svg += '<path d="M' + x1 + ',' + y1 + ' C' + cx + ',' + y1 + ' ' + cx + ',' + y2 + ' ' + (x2-1) + ',' + y2 + '" fill="none" stroke="var(--vscode-widget-border)" stroke-width="1.5" marker-end="url(#arrow2)"/>';
                }
            });
        });

        models.forEach(m => {
            if (!pos[m.name]) return;
            const {x,y} = pos[m.name];
            const c = COL[m.materialized] || '#6c7086';
            const isActive = m.name === activeModel;
            const label = m.name.length > 14 ? m.name.slice(0,13) + '\u2026' : m.name;
            svg += '<g class="dag-node" onclick="openModel(\'' + m.name + '\')">';
            svg += '<rect x="' + x + '" y="' + y + '" width="' + NW + '" height="' + NH + '" rx="4" fill="' + (isActive ? c + '33' : 'var(--vscode-sideBar-background)') + '" stroke="' + c + '" stroke-width="' + (isActive ? 2 : 1) + '"/>';
            svg += '<text x="' + (x+NW/2) + '" y="' + (y+NH/2+4) + '" text-anchor="middle" font-size="10" font-family="var(--vscode-editor-font-family)" fill="' + (isActive ? c : 'var(--vscode-editor-foreground)') + '" font-weight="' + (isActive ? '600' : '400') + '">' + label + '</text>';
            svg += '</g>';
        });
        svg += '</svg>';

        const legendHtml = '<div class="dag-legend">' + Object.entries(COL).map(([k,v]) => '<div class="dag-legend-item"><div class="dag-legend-dot" style="background:' + v + '"></div>' + k + '</div>').join('') + '</div>';
        document.getElementById('dag').innerHTML = legendHtml + svg;
    }

    function setMode(mode) {
        currentMode = mode;
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
        document.getElementById('btn-' + mode).classList.add('active');
        document.getElementById('content').style.display = (mode === 'dag') ? 'none' : 'block';
        document.getElementById('dag').style.display = (mode === 'cards') ? 'none' : 'block';
        if (mode === 'dag' || mode === 'both') renderDag();
    }

    function openModel(name) {
        const m = models.find(x => x.name === name);
        if (m && m.path) {
            vscodeApi.postMessage({ command: 'openFile', path: m.path });
        }
    }

    // Initial render
    renderCards();
    </script>
    </body></html>`;
}

module.exports = { activate, deactivate };
