'use strict';
const vscode = require('vscode');
const path = require('path');
const cp = require('child_process');

// ── Globals ────────────────────────────────────────────────────────────────
let outputChannel;
let statusBarItem;
let modelTreeProvider;

// ── Activation ─────────────────────────────────────────────────────────────
function activate(context) {
    outputChannel = vscode.window.createOutputChannel('KelpMesh');
    context.subscriptions.push(outputChannel);

    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.text = '$(database) KelpMesh';
    statusBarItem.tooltip = 'KelpMesh — click to show lineage';
    statusBarItem.command = 'kelpmesh.showLineage';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

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
        'kelpmesh.runProject':    () => runProjectCmd(),
        'kelpmesh.scanProject':   () => scanProjectCmd(),
        'kelpmesh.openStudio':    () => openStudioCmd(),
        'kelpmesh.refreshModels': () => modelTreeProvider.refresh(),
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
    // Try VS Code Python extension's active interpreter
    const pythonExt = vscode.extensions.getExtension('ms-python.python');
    if (pythonExt?.isActive) {
        const interp = pythonExt.exports?.settings?.getExecutionDetails?.()?.execCommand;
        if (interp?.[0]) return interp[0];
    }
    return process.execPath;
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
    statusBarItem.text = `$(database) KelpMesh ${text}`;
    statusBarItem.tooltip = tooltip || text;
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
            setTimeout(() => setStatus(''), 4000);
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
    setTimeout(() => setStatus(''), 4000);
}

async function showLineageCmd() {
    const python = getPython();
    const projectDir = getProjectDir();
    if (!projectDir) return;

    const editor = vscode.window.activeTextEditor;
    const activeModel = editor ? modelNameFrom(editor.document) : '';

    let manifest = { models: [] };
    try {
        const out = cp.execSync(
            `"${python}" -m kelpmesh docs-manifest`,
            { cwd: projectDir, encoding: 'utf8', timeout: 30000 }
        );
        manifest = JSON.parse(out);
    } catch (_) {}

    const panel = vscode.window.createWebviewPanel(
        'kelpmeshLineage', 'KelpMesh Lineage', vscode.ViewColumn.Beside,
        { enableScripts: false }
    );
    panel.webview.html = buildLineageHtml(manifest.models || [], activeModel);
}

async function runProjectCmd() {
    await runKM(['run'], { title: 'run all models' });
}

async function scanProjectCmd() {
    await runKM(['scan', 'pii'], { title: 'scan for PII' });
}

async function openStudioCmd() {
    const python = getPython();
    const projectDir = getProjectDir();
    if (!projectDir) return;

    // Start studio in background and open browser
    const child = cp.spawn(python, ['-m', 'kelpmesh', 'studio'], {
        cwd: projectDir,
        detached: true,
        stdio: 'ignore',
    });
    child.unref();

    setTimeout(() => {
        vscode.env.openExternal(vscode.Uri.parse('http://localhost:8501'));
    }, 2000);

    vscode.window.showInformationMessage(
        'KelpMesh Studio starting at http://localhost:8501…',
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

    // Warn on hardcoded credentials
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

    // Warn on {{ ref( without closing }}
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
        return [
            new vscode.CodeLens(top, { title: '$(play) Run',     command: 'kelpmesh.runModel' }),
            new vscode.CodeLens(top, { title: '$(beaker) Test',  command: 'kelpmesh.testModel' }),
            new vscode.CodeLens(top, { title: '$(eye) Preview',  command: 'kelpmesh.previewModel' }),
            new vscode.CodeLens(top, { title: '$(code) Compile', command: 'kelpmesh.compileModel' }),
            new vscode.CodeLens(top, { title: '$(type-hierarchy) Lineage', command: 'kelpmesh.showLineage' }),
        ];
    }
}

// ── Model Tree View ────────────────────────────────────────────────────────
class ModelTreeProvider {
    constructor() { this._onDidChangeTreeData = new vscode.EventEmitter(); this.onDidChangeTreeData = this._onDidChangeTreeData.event; }
    refresh() { this._onDidChangeTreeData.fire(); }

    getTreeItem(element) {
        const item = new vscode.TreeItem(element.label, vscode.TreeItemCollapsibleState.None);
        item.description = element.materialized || '';
        item.iconPath = new vscode.ThemeIcon(element.type === 'python' ? 'symbol-method' : 'symbol-file');
        item.command = { command: 'vscode.open', title: 'Open', arguments: [element.uri] };
        item.tooltip = `${element.label} (${element.materialized || 'view'})`;
        return item;
    }

    async getChildren() {
        const projectDir = getProjectDir();
        if (!projectDir) return [];
        const modelsDir = path.join(projectDir, 'models');
        try {
            const { readdirSync, statSync } = require('fs');
            const files = readdirSync(modelsDir, { recursive: true })
                .filter(f => /\.(sql|py)$/.test(f))
                .map(f => {
                    const fullPath = path.join(modelsDir, f);
                    const label = path.basename(f).replace(/\.(sql|py)$/, '');
                    const type = f.endsWith('.py') ? 'python' : 'sql';
                    return { label, uri: vscode.Uri.file(fullPath), type, materialized: '' };
                });
            return files;
        } catch (_) { return []; }
    }
}

// ── HTML builders ──────────────────────────────────────────────────────────
function vsStyles() {
    return `
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:13px;padding:16px;background:var(--vscode-editor-background);color:var(--vscode-editor-foreground)}
        h2{font-size:1.1rem;margin-bottom:12px;font-weight:600}
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

function buildLineageHtml(models, activeModel) {
    const cards = models.map(m => {
        const active = m.name === activeModel;
        const up = (m.upstream || []).map(u => `<span class="dep-chip">${u}</span>`).join('');
        const dn = (m.downstream || []).map(d => `<span class="dep-chip">${d}</span>`).join('');
        return `<div class="model-card${active ? ' active' : ''}">
            <strong>${m.name}</strong><span class="badge">${m.materialized || 'view'}</span>
            ${up ? `<div class="dep-label">Upstream</div><div class="dep-list">${up}</div>` : ''}
            ${dn ? `<div class="dep-label">Downstream</div><div class="dep-list">${dn}</div>` : ''}
        </div>`;
    }).join('');

    return `<!DOCTYPE html><html><head><style>${vsStyles()}</style></head><body>
        <h2>KelpMesh Lineage</h2>
        ${cards || '<p style="color:var(--vscode-descriptionForeground)">No models found. Run <code>kelpmesh docs-manifest</code> first.</p>'}
        </body></html>`;
}

module.exports = { activate, deactivate };
