'use strict';
// Load the extracted, platform-specific VSIX in a real VS Code with an isolated home.
const { runTests } = require('@vscode/test-electron');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '../..');
  const directory = path.join(root, 'artifacts/qa/native-vscode');
  const home = path.join(directory, 'home');
  const repository = path.join(directory, 'repo with spaces');
  await fs.mkdir(home, { recursive: true });
  await fs.mkdir(repository, { recursive: true });
  const local = path.join(home, 'Local');
  const data = process.platform === 'darwin' ? path.join(home, 'Library/Application Support/Agentboard') : path.join(local, 'Agentboard');
  const environment = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('VSCODE_') && key !== 'ELECTRON_RUN_AS_NODE' && key !== 'AGENTBOARD_TOKEN'));
  await runTests({
    extensionDevelopmentPath: path.join(root, 'build/installed-vsix/extension'),
    extensionTestsPath: path.join(__dirname, 'actual-driver.cjs'),
    extensionTestsEnv: { ...environment, HOME: home, LOCALAPPDATA: local,
      USERNAME: 'DashAI-Native-QA', DASHAI_VSCODE_QA: directory, DASHAI_NATIVE_SMOKE: '1', DASHAI_EXPECT_DATA: data },
    launchArgs: [repository, '--user-data-dir', path.join(directory, 'profile'),
      '--extensions-dir', path.join(directory, 'extensions'), '--disable-workspace-trust',
      '--skip-welcome', '--skip-release-notes', '--disable-updates', '--disable-telemetry'],
  });
  const result = JSON.parse(await fs.readFile(path.join(directory, 'driver-complete.json'), 'utf8'));
  assert.equal(result.status, 'passed');
  console.log('Native VS Code activation, permanent runtime, connector setup and restart: PASS', result);
})().catch(error => { console.error(error); process.exitCode = 1; });
