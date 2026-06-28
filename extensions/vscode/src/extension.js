const vscode = require('vscode');
const path = require('path');
const { execSync, exec } = require('child_process');

let lineagePanel = undefined;
let statusBarItem = undefined;

function activate(context) {
    console.log('briq extension activating...');

    statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Left, 100
    );
    statusBarItem.text = '$(database) briq';
    statusBarItem.tooltip = 'briq - SQL Transformation Platform';
    statusBarItem.command = 'briq.showLineage';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    context.subscriptions.push(
        vscode.commands.registerCommand('briq.runModel', runModel)
    );
    context.subscriptions.push(
        vscode.commands.registerCommand('briq.testModel', testModel)
    );
    context.subscriptions.push(
        vscode.commands.registerCommand('briq.previewModel', previewModel)
    );
    context.subscriptions.push(
        vscode.commands.registerCommand('briq.showLineage', showLineage)
    );
    context.subscriptions.push(
        vscode.commands.registerCommand('briq.buildProject', buildProject)
    );
    context.subscriptions.push(
        vscode.commands.registerCommand('briq.openDocs', openDocs)
    );

    vscode.languages.registerCodeLensProvider(
        { language: 'sql', scheme: 'file' },
        new BriqCodeLensProvider()
    );

    vscode.workspace.onDidSaveTextDocument((doc) => {
        if (doc.languageId === 'sql' && doc.uri.scheme === 'file') {
            checkModelForIssues(doc);
        }
    });

    console.log('briq extension activated!');
}

function deactivate() {
    if (lineagePanel) {
        lineagePanel.dispose();
    }
}

function getProjectDir() {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
        vscode.window.showErrorMessage('briq: No workspace folder open');
        return null;
    }
    return workspaceFolders[0].uri.fsPath;
}

function getModelName(document) {
    const fileName = path.basename(document.fileName, '.sql');
    return fileName;
}

function runBriqCommand(args) {
    const projectDir = getProjectDir();
    if (!projectDir) return null;

    try {
        const cmd = `"${process.execPath}" -m briq ${args} --project-dir "${projectDir}"`;
        const result = execSync(cmd, { encoding: 'utf8', timeout: 120000 });
        return { success: true, output: result };
    } catch (error) {
        return { success: false, output: error.stdout || error.message };
    }
}

async function runModel() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;

    const modelName = getModelName(editor.document);
    vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: `briq: Running ${modelName}...` },
        async () => {
            const result = runBriqCommand(`run ${modelName}`);
            if (result.success) {
                vscode.window.showInformationMessage(`briq: ${modelName} ran successfully`);
            } else {
                vscode.window.showErrorMessage(`briq: ${modelName} failed - ${result.output}`);
            }
        }
    );
}

async function testModel() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;

    const modelName = getModelName(editor.document);
    vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: `briq: Testing ${modelName}...` },
        async () => {
            const result = runBriqCommand(`test ${modelName}`);
            if (result.success) {
                vscode.window.showInformationMessage(`briq: ${modelName} tests passed`);
            } else {
                vscode.window.showErrorMessage(`briq: ${modelName} tests failed - ${result.output}`);
            }
        }
    );
}

async function previewModel() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;

    const modelName = getModelName(editor.document);
    const result = runBriqCommand(`preview ${modelName}`);
    if (result.success) {
        const panel = vscode.window.createWebviewPanel(
            'briqPreview',
            `briq Preview: ${modelName}`,
            vscode.ViewColumn.Beside,
            {}
        );
        panel.webview.html = getPreviewHtml(modelName, result.output);
    } else {
        vscode.window.showErrorMessage(`briq: Preview failed - ${result.output}`);
    }
}

function showLineage() {
    const projectDir = getProjectDir();
    if (!projectDir) return;

    const panel = vscode.window.createWebviewPanel(
        'briqLineage',
        'briq Lineage',
        vscode.ViewColumn.Beside,
        { enableScripts: true }
    );

    const editor = vscode.window.activeTextEditor;
    const modelName = editor ? getModelName(editor.document) : '';

    panel.webview.html = getLineageHtml(projectDir, modelName);
}

async function buildProject() {
    vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'briq: Building project...' },
        async () => {
            const result = runBriqCommand('build');
            if (result.success) {
                vscode.window.showInformationMessage('briq: Build completed');
            } else {
                vscode.window.showErrorMessage(`briq: Build failed - ${result.output}`);
            }
        }
    );
}

async function openDocs() {
    const projectDir = getProjectDir();
    if (!projectDir) return;

    const result = runBriqCommand('docs');
    if (result.success) {
        const docsPath = path.join(projectDir, 'target', 'docs', 'index.html');
        vscode.env.openExternal(vscode.Uri.file(docsPath));
    }
}

function checkModelForIssues(document) {
    const modelName = getModelName(document);
    const text = document.getText();

    const diagnostics = [];
    const lines = text.split('\n');

    if (!text.trim().toUpperCase().startsWith('SELECT')) {
        diagnostics.push({
            severity: vscode.DiagnosticSeverity.Warning,
            message: 'briq: Model should start with a SELECT statement',
            range: new vscode.Range(0, 0, 0, 10),
        });
    }

    const diagnosticCollection = vscode.languages.createDiagnosticCollection('briq');
    diagnosticCollection.set(document.uri, diagnostics);
}

class BriqCodeLensProvider {
    provideCodeLenses(document, token) {
        const modelName = getModelName(document);
        return [
            new vscode.CodeLens(
                new vscode.Range(0, 0, 0, 0),
                { title: `$(play) Run ${modelName}`, command: 'briq.runModel' }
            ),
            new vscode.CodeLens(
                new vscode.Range(0, 0, 0, 0),
                { title: `$(beaker) Test ${modelName}`, command: 'briq.testModel' }
            ),
            new vscode.CodeLens(
                new vscode.Range(0, 0, 0, 0),
                { title: `$(eye) Preview 100`, command: 'briq.previewModel' }
            ),
            new vscode.CodeLens(
                new vscode.Range(0, 0, 0, 0),
                { title: `$(graph) Lineage`, command: 'briq.showLineage' }
            ),
        ];
    }
}

function getLineageHtml(projectDir, activeModel) {
    let result;
    try {
        const cmd = `"${process.execPath}" -m briq docs-manifest --project-dir "${projectDir}"`;
        result = execSync(cmd, { encoding: 'utf8', timeout: 30000 });
    } catch (e) {
        result = '{"models":[]}';
    }

    const manifest = JSON.parse(result);
    const models = manifest.models || [];

    let modelCards = models.map(m => {
        const isActive = m.name === activeModel;
        const upstream = m.upstream || [];
        const downstream = m.downstream || [];
        const columns = m.columns || [];

        return `
        <div class="model-card ${isActive ? 'active' : ''}" id="model-${m.name}">
            <div class="model-header">
                <strong>${m.name}</strong>
                <span class="badge">${m.materialized || 'view'}</span>
            </div>
            <div class="model-deps">
                <div class="dep-section">
                    <div class="dep-label">Upstream (${upstream.length})</div>
                    <div class="dep-list">${upstream.map(u => `<a href="#model-${u}">${u}</a>`).join('') || '<span class="none">source</span>'}</div>
                </div>
                <div class="dep-section">
                    <div class="dep-label">Downstream (${downstream.length})</div>
                    <div class="dep-list">${downstream.map(d => `<a href="#model-${d}">${d}</a>`).join('') || '<span class="none">none</span>'}</div>
                </div>
            </div>
            ${columns.length ? `
            <details>
                <summary>Columns (${columns.length})</summary>
                <div class="column-list">${columns.map(c => `<div class="column-item"><code>${c.name}</code></div>`).join('')}</div>
            </details>` : ''}
        </div>`;
    }).join('');

    let mermaidGraph = 'graph TD;\n';
    models.forEach(m => {
        (m.upstream || []).forEach(u => {
            mermaidGraph += `    ${u}-->${m.name};\n`;
        });
    });

    return `<!DOCTYPE html>
<html>
<head><style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 16px; background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); }
    h1 { font-size: 1.2rem; margin-bottom: 12px; }
    .model-card { background: var(--vscode-sideBar-background); border: 1px solid var(--vscode-widget-border); border-radius: 6px; padding: 12px; margin-bottom: 8px; }
    .model-card.active { border-color: var(--vscode-focusBorder); }
    .model-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .badge { background: var(--vscode-badge-background); color: var(--vscode-badge-foreground); padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
    .dep-section { margin: 4px 0; }
    .dep-label { font-size: 0.75rem; color: var(--vscode-descriptionForeground); }
    .dep-list { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 2px; }
    .dep-list a { color: var(--vscode-textLink-foreground); text-decoration: none; font-size: 0.85rem; padding: 1px 6px; border-radius: 3px; background: var(--vscode-badge-background); }
    .dep-list a:hover { text-decoration: underline; }
    .none { font-size: 0.8rem; color: var(--vscode-disabledForeground); font-style: italic; }
    details { margin-top: 6px; }
    summary { cursor: pointer; font-size: 0.8rem; color: var(--vscode-textLink-foreground); }
    .column-item { padding: 2px 0; }
    .column-item code { font-size: 0.8rem; }
    .graph-container { margin-top: 16px; padding: 12px; background: var(--vscode-sideBar-background); border: 1px solid var(--vscode-widget-border); border-radius: 6px; }
</style></head>
<body>
    <h1>$(database) briq Lineage</h1>
    <div class="graph-container">
        <div class="mermaid">${mermaidGraph}</div>
    </div>
    ${modelCards}
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script>mermaid.initialize({startOnLoad:true,theme:'dark',themeVariables:{background:'transparent'}});</script>
</body>
</html>`;
}

function getPreviewHtml(modelName, data) {
    const rows = data.split('\n').filter(l => l.trim());
    const tableRows = rows.map(r => {
        const cols = r.split('|').map(c => c.trim());
        return `<tr>${cols.map(c => `<td>${c}</td>`).join('')}</tr>`;
    }).join('');

    return `<!DOCTYPE html>
<html>
<head>
<style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 16px; }
    h2 { margin-bottom: 12px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--vscode-widget-border); }
    th { font-weight: 600; }
</style>
</head>
<body>
    <h2>Preview: ${modelName}</h2>
    <table>${tableRows}</table>
</body>
</html>`;
}

module.exports = { activate, deactivate };
