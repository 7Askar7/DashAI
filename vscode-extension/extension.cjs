'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const { spawn, execFile } = require('node:child_process');
const { promisify } = require('node:util');
const runFile = promisify(execFile);
const updates = require('./updates.cjs');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let heartbeat;

function parseRuntime(value, dataDir) {
  if (value?.schema_version !== 1 || !/^http:\/\/127\.0\.0\.1:([1-9]\d{0,4})$/.test(value.base_url || '') ||
      Number(new URL(value.base_url).port) > 65535 || typeof value.data_dir !== 'string' ||
      path.resolve(value.data_dir).toLowerCase() !== path.resolve(dataDir).toLowerCase() ||
      !/^[a-f0-9-]{36}$/.test(value.instance_id || '') || !/^(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})$/.test(value.version || '') ||
      !Number.isSafeInteger(value.pid) || value.pid <= 0 || !['desktop', 'vscode'].includes(value.mode)) {
    throw new Error('Файл запуска DashAI устарел или некорректен.');
  }
  return value;
}

function requestJson(url, method = 'GET', headers = {}, maxBytes = 64 * 1024 * 1024) {
  return new Promise((resolve, reject) => {
    const request = http.request(url, { method, headers }, response => {
      let size = 0;
      const parts = [];
      response.on('data', chunk => {
        size += chunk.length;
        if (size > maxBytes) response.destroy(new Error('Ответ DashAI превышает допустимый размер.'));
        else parts.push(chunk);
      });
      response.on('error', reject);
      response.on('end', () => {
        try {
          const result = JSON.parse(Buffer.concat(parts).toString('utf8'));
          if (response.statusCode !== 200) throw new Error(result.detail || 'DashAI недоступен.');
          resolve(result);
        } catch (error) { reject(error); }
      });
    });
    request.setTimeout(10000, () => request.destroy(new Error('Нет ответа от локального DashAI.')));
    request.on('error', reject);
    request.end();
  });
}

async function discover(dataDir) {
  try {
    const runtime = parseRuntime(JSON.parse(await fs.readFile(path.join(dataDir, 'runtime.json'), 'utf8')), dataDir);
    const health = await requestJson(runtime.base_url + '/api/health', 'GET', {}, 16384);
    if (health.status !== 'ok' || health.instance_id !== runtime.instance_id || health.pid !== runtime.pid ||
        health.version !== runtime.version || health.mode !== runtime.mode || typeof health.mcp_running !== 'boolean') return null;
    return { ...runtime, mcp_running: health.mcp_running === true };
  } catch { return null; }
}

const needsRuntimeUpgrade = (runtime, version) => runtime.mode === 'vscode' && !runtime.mcp_running && runtime.version.localeCompare(version, 'en', { numeric: true }) < 0;

async function copyRuntime(extensionDir, dataDir, version) {
  const parent = path.join(dataDir, 'vscode-runtime');
  const destination = path.join(parent, version);
  const marker = path.join(destination, '_internal', 'package.json');
  try {
    if (JSON.parse(await fs.readFile(marker, 'utf8')).version === version) return destination;
  } catch {}
  await fs.mkdir(parent, { recursive: true });
  const staging = path.join(parent, 'staging-' + crypto.randomUUID());
  try {
    await fs.cp(path.join(extensionDir, 'runtime', 'Agentboard'), staging, { recursive: true });
    if (JSON.parse(await fs.readFile(path.join(staging, '_internal', 'package.json'), 'utf8')).version !== version) {
      throw new Error('Версия встроенного приложения не совпадает с расширением.');
    }
    // Windows antivirus can briefly lock copied EXEs; keep the directory commit atomic.
    for (let attempt = 0; ; attempt++) {
      try { await fs.rename(staging, destination); break; }
      catch (error) {
        let installed;
        try { installed = JSON.parse(await fs.readFile(marker, 'utf8')).version; } catch {}
        if (installed === version) break;
        if (attempt === 31 || !['EPERM', 'EBUSY'].includes(error.code)) throw error;
        await delay(250);
      }
    }
    return destination;
  } finally {
    // Only our UUID staging copy is removed; persisted data and older MCP paths stay intact.
    await fs.rm(staging, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
  }
}

async function stopRuntime(runtime) {
  if (runtime.mode !== 'vscode') throw new Error('Настольный DashAI закрывается через его окно.');
  await requestJson(runtime.base_url + '/api/desktop/stop', 'POST', {
    'X-Agentboard-Instance': runtime.instance_id,
  });
}

function boardHtml(runtime) {
  const nonce = crypto.randomBytes(24).toString('hex');
  const origin = runtime.base_url;
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src ${origin}; script-src 'nonce-${nonce}'; style-src 'nonce-${nonce}'">
    <style nonce="${nonce}">html,body,iframe{height:100%;width:100%;margin:0;padding:0;border:0}body{overflow:hidden;background:#10161d}</style>
    </head><body><iframe id="board" title="DashAI: проекты, задачи и история" src="${origin}/?vscode=1" allow="clipboard-read; clipboard-write"></iframe>
    <script nonce="${nonce}">
      const host = acquireVsCodeApi();
      const frame = document.getElementById('board');
      const origin = ${JSON.stringify(origin)};
      window.addEventListener('message', event => {
        if (event.source === frame.contentWindow && event.origin === origin && event.data?.kind === 'agentboard-host') {
          host.postMessage(event.data);
        } else if (event.source !== frame.contentWindow && event.origin === window.location.origin && event.data?.kind === 'agentboard-host-result') {
          frame.contentWindow.postMessage(event.data, origin);
        }
      });
    </script></body></html>`;
}

function activate(context) {
  const vscode = require('vscode');
  const version = context.extension.packageJSON.version;
  const dataDir = path.join(process.env.LOCALAPPDATA || path.join(require('node:os').homedir(), 'AppData', 'Local'), 'Agentboard');
  let panel, panelInstance, runtime, starting, checking = false, installedUpdate = false;
  const output = vscode.window.createOutputChannel('DashAI');
  context.subscriptions.push(output);
  const fail = error => {
    output.appendLine(String(error.message || error));
    vscode.window.showErrorMessage('DashAI: ' + (error.message || 'Не удалось выполнить действие.'));
  };

  async function ensureRuntime() {
    if (starting) return starting;
    starting = (async () => {
      if (process.platform !== 'win32' || process.arch !== 'x64') throw new Error('Это расширение предназначено для Windows x64.');
      if (!vscode.workspace.isTrusted) throw new Error('Откройте доверенную папку проекта.');
      let existing = await discover(dataDir);
      if (existing && needsRuntimeUpgrade(existing, version)) {
        // New VSIX uses the shared API's guarded shutdown; never kills another app's PID.
        await stopRuntime(existing);
        for (let i = 0; i < 80 && await discover(dataDir); i++) await delay(250);
        existing = await discover(dataDir);
      }
      if (!existing) {
        const directory = await copyRuntime(context.extensionPath, dataDir, version);
        const child = spawn(path.join(directory, 'Agentboard.exe'), ['--vscode', '--data-dir', dataDir], {
          cwd: directory, windowsHide: true, detached: true, stdio: 'ignore',
        });
        let spawnError;
        child.on('error', error => { spawnError = error; });
        child.unref();
        for (let i = 0; i < 160; i++) {
          if (spawnError) throw spawnError;
          existing = await discover(dataDir);
          if (existing) break;
          await delay(250);
        }
        if (!existing) throw new Error('Не удалось запустить доску. Если открыт Agentboard 1.3 или старше, закройте его окно и повторите. Журнал: ' + path.join(dataDir, 'logs', 'desktop.log'));
      }
      runtime = existing;
      if (existing.version !== version) {
        vscode.window.showInformationMessage(`Доска работает на версии ${existing.version}. Новая версия применится после завершения MCP-сессий и повторного открытия доски.`);
      }
      if (!heartbeat) heartbeat = setInterval(() => {
        if (runtime) requestJson(runtime.base_url + '/api/health', 'GET', {}, 16384).catch(() => {});
      }, 30000);
      return runtime;
    })();
    try { return await starting; } finally { starting = null; }
  }

  async function bridge(message, activeRuntime) {
    if (message?.kind !== 'agentboard-host' || typeof message.id !== 'string' || message.id.length > 100) return;
    let result, error;
    try {
      if (message.action === 'clipboard' && typeof message.text === 'string' && message.text.length <= 200000) {
        await vscode.env.clipboard.writeText(message.text);
        result = true;
      } else if (message.action === 'export' && /^[a-f0-9-]{36}$/.test(message.project_id || '')) {
        const destination = await vscode.window.showSaveDialog({
          defaultUri: vscode.Uri.file(path.join(require('node:os').homedir(), `dashai-${message.project_id}.json`)),
          filters: { JSON: ['json'] }, saveLabel: 'Экспортировать проект',
        });
        if (!destination) result = false;
        else {
          const snapshot = await requestJson(activeRuntime.base_url + '/api/projects/' + message.project_id + '/export');
          await vscode.workspace.fs.writeFile(destination, Buffer.from(JSON.stringify(snapshot, null, 2), 'utf8'));
          result = true;
        }
      } else throw new Error('Некорректная команда доски.');
    } catch (failure) { error = failure.message || 'Не удалось выполнить действие.'; }
    if (panel) await panel.webview.postMessage({ kind: 'agentboard-host-result', id: message.id, result, error });
  }

  async function open() {
    const active = await ensureRuntime();
    if (panel) {
      panel.reveal(vscode.ViewColumn.Active);
      if (panelInstance !== active.instance_id) panel.webview.html = boardHtml(active);
    }
    else {
      panel = vscode.window.createWebviewPanel('agentboard.board', 'DashAI', vscode.ViewColumn.Active, {
        enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [],
      });
      panel.iconPath = vscode.Uri.joinPath(context.extensionUri, 'assets', 'agentboard.svg');
      panel.onDidDispose(() => { panel = null; });
      panel.webview.onDidReceiveMessage(message => bridge(message, runtime));
      panel.webview.html = boardHtml(active);
    }
    panelInstance = active.instance_id;
  }

  async function connectAgents() {
    await ensureRuntime();
    let folder;
    if (vscode.workspace.workspaceFolders?.length === 1) folder = vscode.workspace.workspaceFolders[0];
    else if (vscode.workspace.workspaceFolders?.length) folder = await vscode.window.showWorkspaceFolderPick({ placeHolder: 'Проект для Codex и Claude Code' });
    else folder = (await vscode.window.showOpenDialog({ canSelectFiles: false, canSelectFolders: true, canSelectMany: false, openLabel: 'Подключить агентов' }))?.[0];
    const uri = folder?.uri || folder;
    if (!uri) return;
    if (uri.scheme !== 'file') throw new Error('Подключение доступно для локальной папки Windows.');
    const directory = await copyRuntime(context.extensionPath, dataDir, version);
    await runFile(path.join(directory, 'AgentboardMCP.exe'), ['--setup-connectors', '--project-root', uri.fsPath, '--data-dir', dataDir], {
      cwd: directory, windowsHide: true, timeout: 30000, maxBuffer: 1024 * 1024,
    });
    vscode.window.showInformationMessage('Конфигурации Codex и Claude Code сохранены. Начните новую сессию клиента и разрешите project MCP, если он запросит доступ.');
  }

  async function checkUpdates(manual = false) {
    if (checking || installedUpdate) return;
    checking = true;
    try {
      const config = JSON.parse(await fs.readFile(path.join(context.extensionPath, 'update-channel.json'), 'utf8'));
      const manifest = await updates.checkUpdate(config, version);
      if (!manifest) {
        if (manual) vscode.window.showInformationMessage('Установлена актуальная версия DashAI.');
        return;
      }
      const file = await updates.downloadUpdate(manifest, path.join(dataDir, 'vscode-updates'));
      await vscode.commands.executeCommand('workbench.extensions.installExtension', vscode.Uri.file(file));
      installedUpdate = true;
      const selected = await vscode.window.showInformationMessage(`DashAI ${manifest.version} установлен. Перезагрузите окно VS Code, чтобы открыть новую версию.`, 'Перезагрузить окно');
      if (selected) await vscode.commands.executeCommand('workbench.action.reloadWindow');
    } catch (error) {
      output.appendLine('Проверка обновлений: ' + error.message);
      if (manual) fail(error);
    } finally { checking = false; }
  }

  const command = (name, action) => context.subscriptions.push(vscode.commands.registerCommand(name, () => action().catch(fail)));
  command('agentboard.open', open);
  command('agentboard.connectAgents', connectAgents);
  command('agentboard.checkUpdates', () => checkUpdates(true));
  command('agentboard.stop', async () => {
    const active = await discover(dataDir);
    if (!active) return;
    await stopRuntime(active);
    runtime = null;
    panel?.dispose();
    vscode.window.showInformationMessage('Локальная доска остановлена. Данные сохранены.');
  });
  context.subscriptions.push(vscode.window.registerTreeDataProvider('agentboard.launcher', {
    getTreeItem: item => item, getChildren: () => [],
  }));
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 10);
  status.text = '$(project) DashAI';
  status.tooltip = 'Открыть проекты, задачи и историю';
  status.command = 'agentboard.open';
  status.show();
  context.subscriptions.push(status);
  const updateTimer = setInterval(() => {
    if (vscode.workspace.getConfiguration('agentboard').get('automaticUpdates', true)) checkUpdates();
  }, 60 * 60 * 1000);
  context.subscriptions.push({ dispose: () => { clearInterval(updateTimer); clearInterval(heartbeat); heartbeat = undefined; panel?.dispose(); } });
  if (vscode.workspace.getConfiguration('agentboard').get('automaticUpdates', true)) checkUpdates();
  return { dataDir, discover: () => discover(dataDir) };
}

function deactivate() { clearInterval(heartbeat); heartbeat = undefined; }
module.exports = { activate, deactivate, parseRuntime, discover, copyRuntime, boardHtml, requestJson, needsRuntimeUpgrade };
