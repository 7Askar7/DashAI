'use strict';
// Official VS Code extension-test entry point; a separate QA profile is required.
const vscode = require('vscode');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

exports.run = async function () {
  const directory = process.env.DASHAI_VSCODE_QA;
  assert(directory, 'Run through scripts/vscode_smoke.py with an isolated profile.');
  const write = (name, value) => fs.writeFile(path.join(directory, name), JSON.stringify(value));
  const extension = vscode.extensions.getExtension('7askar7.agentboard');
  assert(extension, 'VSIX is installed in the isolated extension directory');
  // VS Code returns a separate API object per extension; stub the installed product's API.
  const productAPI = createRequire(path.join(extension.extensionPath, 'extension.cjs'))('vscode');
  const originalSaveDialog = productAPI.window.showSaveDialog;
  const originalClipboard = await vscode.env.clipboard.readText();
  productAPI.window.showSaveDialog = async () => vscode.Uri.file(path.join(directory, 'project-export.json'));
  let lastCommand = 0;
  try {
    const api = await extension.activate();
    await vscode.commands.executeCommand('agentboard.open');
    let runtime = await api.discover();
    assert(runtime && runtime.mode === 'vscode' && runtime.version === extension.packageJSON.version);
    await vscode.commands.executeCommand('agentboard.connectAgents');
    assert(await fs.stat(path.join(vscode.workspace.workspaceFolders[0].uri.fsPath, '.mcp.json')));
    await write('ready.json', { runtime, vscode: vscode.version, extensionPath: extension.extensionPath });
    const deadline = Date.now() + 8 * 60 * 1000;
    while (Date.now() < deadline) {
      await pause(100);
      let command;
      try { command = JSON.parse(await fs.readFile(path.join(directory, 'command.json'), 'utf8')); }
      catch { continue; }
      if (command.id <= lastCommand) continue;
      lastCommand = command.id;
      try {
        if (command.action === 'clipboard') {
          assert.equal(await vscode.env.clipboard.readText(), command.expected);
        } else if (command.action === 'export') {
          const snapshot = JSON.parse(await fs.readFile(path.join(directory, 'project-export.json'), 'utf8'));
          assert.equal(snapshot.project.id, command.project_id);
          assert(snapshot.tasks.some(task => task.title === command.task_title));
          assert(snapshot.events?.length || snapshot.activity?.length || snapshot.history?.length,
            'Export contains audit history');
        } else if (command.action === 'blocked-stop') {
          await vscode.commands.executeCommand('agentboard.stop');
          assert.equal((await api.discover()).instance_id, runtime.instance_id, 'Active MCP prevents shutdown');
        } else if (command.action === 'restart') {
          await vscode.commands.executeCommand('agentboard.stop');
          for (let i = 0; i < 80 && await api.discover(); i++) await pause(250);
          assert.equal(await api.discover(), null);
          await vscode.commands.executeCommand('agentboard.open');
          const next = await api.discover();
          assert(next && next.instance_id !== runtime.instance_id && next.data_dir === runtime.data_dir);
          runtime = next;
          await write('runtime-after-restart.json', runtime);
        } else if (command.action === 'finish') {
          await vscode.commands.executeCommand('agentboard.stop');
          await write('driver-complete.json', { status: 'passed', vscode: vscode.version });
          await write('reply.json', { id: command.id, status: 'passed' });
          return;
        } else throw new Error('Unknown QA action');
        await write('reply.json', { id: command.id, status: 'passed' });
      } catch (error) {
        await write('reply.json', { id: command.id, status: 'failed', error: error.message });
        throw error;
      }
    }
    throw new Error('QA driver timed out');
  } catch (error) {
    await write('driver-error.json', { error: error.stack || String(error) });
    throw error;
  } finally {
    productAPI.window.showSaveDialog = originalSaveDialog;
    await vscode.env.clipboard.writeText(originalClipboard);
  }
};
