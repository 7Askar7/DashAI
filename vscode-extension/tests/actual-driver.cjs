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
  const native = process.env.DASHAI_NATIVE_SMOKE === '1';
  const progress = async stage => {
    if (!native) return;
    console.log('DashAI native QA:', stage);
    await write('driver-progress.json', { stage, time: Date.now() });
  };
  await progress('driver started');
  // GitHub VSIX keeps the original ID; the Marketplace build is published as dashai.
  const extension = vscode.extensions.getExtension('7askar7.agentboard') || vscode.extensions.getExtension('7askar7.dashai');
  assert(extension, 'VSIX is installed in the isolated extension directory');
  // Only the interactive export QA needs to replace the installed product's save dialog.
  const productAPI = native ? null : createRequire(path.join(extension.extensionPath, 'extension.cjs'))('vscode');
  const originalSaveDialog = productAPI?.window.showSaveDialog;
  const originalClipboard = native ? null : await vscode.env.clipboard.readText();
  if (productAPI) productAPI.window.showSaveDialog = async options => {
    const name = path.basename(options.defaultUri.fsPath);
    return vscode.Uri.file(path.join(directory, name.startsWith('dashai-documentation.') ? name : 'project-export.json'));
  };
  let lastCommand = 0;
  const activationTimer = native ? setInterval(() => {
    write('driver-activation.json', { isActive: extension.isActive, hasExports: extension.isActive && !!extension.exports }).catch(console.error);
  }, 5000) : null;
  try {
    let api;
    if (native) {
      assert(vscode.workspace.isTrusted, 'The isolated local QA workspace is trusted.');
      assert(extension.packageJSON.activationEvents.includes('onStartupFinished'));
      assert(extension.packageJSON.contributes.commands.some(command => command.command === 'agentboard.open'));
      // The test entry can run before workbench startup finishes. Verify natural startup
      // activation before sending a renderer command; never activate the product ourselves.
      await progress('waiting for declared startup activation');
      const startupDeadline = Date.now() + 30000;
      while (!extension.isActive && Date.now() < startupDeadline) await pause(100);
      assert(extension.isActive, 'Declared onStartupFinished activation did not complete within 30 seconds.');
      await progress('opening board through its user command');
      await vscode.commands.executeCommand('agentboard.open');
      api = extension.exports;
    } else {
      api = await extension.activate();
      await vscode.commands.executeCommand('agentboard.open');
    }
    await progress('discovering runtime');
    let runtime = await api.discover();
    assert(runtime && runtime.mode === 'vscode' && runtime.version === extension.packageJSON.version);
    await progress('configuring connectors');
    await vscode.commands.executeCommand('agentboard.connectAgents');
    assert(await fs.stat(path.join(vscode.workspace.workspaceFolders[0].uri.fsPath, '.mcp.json')));
    await write('ready.json', { runtime, vscode: vscode.version, extensionPath: extension.extensionPath });
    if (native) {
      const repository = vscode.workspace.workspaceFolders[0].uri.fsPath;
      const config = JSON.parse(await fs.readFile(path.join(repository, '.mcp.json'), 'utf8')).mcpServers.agentboard;
      assert.equal(path.basename(config.command), process.platform === 'win32' ? 'AgentboardMCP.exe' : 'AgentboardMCP');
      assert(!config.command.startsWith(extension.extensionPath), 'Companion has a durable personal path');
      assert(config.args.includes(runtime.data_dir));
      assert.equal(runtime.data_dir, process.env.DASHAI_EXPECT_DATA);
      await progress('stopping runtime');
      await vscode.commands.executeCommand('agentboard.stop');
      for (let i = 0; i < 80 && await api.discover(); i++) await pause(250);
      assert.equal(await api.discover(), null);
      await progress('restarting runtime');
      await vscode.commands.executeCommand('agentboard.open');
      const next = await api.discover();
      assert(next && next.instance_id !== runtime.instance_id && next.data_dir === runtime.data_dir);
      await vscode.commands.executeCommand('agentboard.stop');
      await write('driver-complete.json', { status: 'passed', platform: process.platform, arch: process.arch, vscode: vscode.version });
      await vscode.commands.executeCommand('workbench.action.quit');
      return;
    }
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
    clearInterval(activationTimer);
    if (productAPI) productAPI.window.showSaveDialog = originalSaveDialog;
    if (originalClipboard !== null) await vscode.env.clipboard.writeText(originalClipboard);
  }
};
