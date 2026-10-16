'use strict';
// Load the extracted, platform-specific VSIX in a real VS Code with an isolated home.
const { runTests } = require('@vscode/test-electron');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '../..');
  const parent = path.join(root, 'artifacts/qa');
  await fs.mkdir(parent, { recursive: true });
  const directory = await fs.mkdtemp(path.join(parent, 'native-vscode-'));
  const home = path.join(directory, 'home');
  const repository = path.join(directory, 'repo with spaces');
  await fs.mkdir(home, { recursive: true });
  await fs.mkdir(repository, { recursive: true });
  const local = path.join(home, 'Local');
  const data = process.platform === 'darwin' ? path.join(home, 'Library/Application Support/Agentboard') : path.join(local, 'Agentboard');
  const environment = { ...process.env };
  for (const key of Object.keys(environment)) {
    if (key.startsWith('VSCODE_') || key === 'ELECTRON_RUN_AS_NODE' || key === 'AGENTBOARD_TOKEN') environment[key] = undefined;
  }
  const extensionPath = path.join(root, 'build/installed-vsix/extension');
  const driver = path.join(extensionPath, 'qa-driver.cjs');
  await fs.copyFile(path.join(__dirname, 'actual-driver.cjs'), driver);
  await runTests({
    cachePath: path.join(root, 'build/vscode-test'),
    extensionDevelopmentPath: extensionPath,
    extensionTestsPath: driver,
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
