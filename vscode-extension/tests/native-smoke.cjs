'use strict';
// Install the platform-specific VSIX in a real VS Code with an isolated home.
const { downloadAndUnzipVSCode, resolveCliArgsFromVSCodeExecutablePath } = require('@vscode/test-electron');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const { promisify } = require('node:util');
const { execFile, spawn } = require('node:child_process');
const runFile = promisify(execFile);
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const root = path.resolve(__dirname, '../..');
  assert(process.platform === 'darwin' && ['arm64', 'x64'].includes(process.arch), 'Run native macOS QA on its target architecture.');
  const version = JSON.parse(await fs.readFile(path.join(root, 'package.json'), 'utf8')).version;
  const vsix = path.join(root, 'artifacts/releases', `DashAI-Marketplace-${version}-darwin-${process.arch}.vsix`);
  const parent = path.join(root, 'artifacts/qa');
  await fs.mkdir(parent, { recursive: true });
  const directory = await fs.mkdtemp(path.join(parent, 'native-vscode-'));
  const home = path.join(directory, 'home');
  const repository = path.join(directory, 'repo with spaces');
  await fs.mkdir(home, { recursive: true });
  await fs.mkdir(repository, { recursive: true });
  const local = path.join(home, 'Local');
  const data = path.join(home, 'Library/Application Support/Agentboard');
  const profile = path.join(directory, 'profile');
  const extensions = path.join(directory, 'extensions');
  const environment = { ...process.env, HOME: home, LOCALAPPDATA: local,
    USERNAME: 'DashAI-Native-QA', DASHAI_VSCODE_QA: directory, DASHAI_NATIVE_SMOKE: '1', DASHAI_EXPECT_DATA: data };
  for (const key of Object.keys(environment)) {
    if (key.startsWith('VSCODE_') || key === 'ELECTRON_RUN_AS_NODE' || key === 'AGENTBOARD_TOKEN') environment[key] = undefined;
  }
  await fs.mkdir(path.join(root, 'build/vscode-test'), { recursive: true });
  const vscodeExecutablePath = await downloadAndUnzipVSCode({ version: '1.142.0', cachePath: path.join(root, 'build/vscode-test') });
  const [cli, ...cliArgs] = resolveCliArgsFromVSCodeExecutablePath(vscodeExecutablePath, { reuseMachineInstall: true });
  const installation = await runFile(cli, [...cliArgs, '--user-data-dir', profile, '--extensions-dir', extensions,
    '--install-extension', vsix, '--force'], { env: environment, timeout: 120000, maxBuffer: 1024 * 1024 });
  await fs.writeFile(path.join(directory, 'install.log'), installation.stdout + installation.stderr);
  const installed = [];
  for (const entry of await fs.readdir(extensions, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name.startsWith('.')) continue;
    const manifest = JSON.parse(await fs.readFile(path.join(extensions, entry.name, 'package.json'), 'utf8'));
    if (`${manifest.publisher}.${manifest.name}`.toLowerCase() === '7askar7.dashai') installed.push(manifest);
  }
  assert.equal(installed.length, 1, 'The official CLI installed DashAI into the isolated extension directory.');
  assert.equal(installed[0].version, version, 'Installed product version matches this checkout.');
  const driver = path.join(directory, 'driver');
  await fs.mkdir(driver);
  await fs.writeFile(path.join(driver, 'package.json'), JSON.stringify({ name: 'dashai-qa', publisher: 'local-qa',
    version: '0.0.1', engines: { vscode: '^1.95.0' }, main: './index.cjs' }));
  await fs.copyFile(path.join(__dirname, 'actual-driver.cjs'), path.join(driver, 'index.cjs'));
  const log = await fs.open(path.join(directory, 'vscode.log'), 'w');
  const child = spawn(vscodeExecutablePath, [repository, '--user-data-dir', profile, '--extensions-dir', extensions,
    '--extensionDevelopmentPath=' + driver, '--extensionTestsPath=' + path.join(driver, 'index.cjs'),
    '--no-sandbox', '--disable-gpu-sandbox', '--no-cached-data', '--disable-workspace-trust',
    '--skip-welcome', '--skip-release-notes', '--disable-updates', '--disable-telemetry', '--log', 'trace'],
  { env: environment, stdio: ['ignore', log.fd, log.fd] });
  let launchError, exit, result, failure;
  child.once('error', error => { launchError = error; });
  const exited = new Promise(resolve => child.once('close', (code, signal) => { exit = { code, signal }; resolve(); }));
  const marker = async name => {
    try { return JSON.parse(await fs.readFile(path.join(directory, name), 'utf8')); }
    catch (error) { if (error.code === 'ENOENT' || error instanceof SyntaxError) return null; throw error; }
  };
  try {
    const deadline = Date.now() + 120000;
    while (Date.now() < deadline) {
      if (launchError) throw launchError;
      const error = await marker('driver-error.json');
      if (error) throw new Error(error.error);
      result = await marker('driver-complete.json');
      if (result) break;
      assert(!exit, 'Isolated VS Code exited before completing the product assertions: ' + JSON.stringify(exit));
      await pause(200);
    }
    assert.equal(result?.status, 'passed', 'Native product assertions did not finish within 120 seconds.');
  } catch (error) {
    failure = error;
    try {
      const names = directory => fs.readdir(directory).catch(error => [error.code]);
      const snapshot = {
        files: await names(data),
        runtimeCopies: await names(path.join(data, 'vscode-runtime')),
        bundle: await names(path.join(data, 'vscode-runtime', version)),
        runtime: await require('../extension.cjs').discover(data),
        desktopLog: await fs.readFile(path.join(data, 'logs/desktop.log'), 'utf8').catch(error => error.code),
      };
      await fs.writeFile(path.join(directory, 'driver-runtime.json'), JSON.stringify(snapshot));
    } catch (diagnosticError) { console.error('Could not snapshot the isolated QA runtime:', diagnosticError); }
  }
  finally {
    let timeout;
    const waitForExit = milliseconds => Promise.race([exited.then(() => true), new Promise(resolve => {
      timeout = setTimeout(() => resolve(false), milliseconds);
    })]).finally(() => clearTimeout(timeout));
    try {
      // Only this spawned QA editor is addressed; success comes from the driver's assertions.
      if (child.pid && child.exitCode === null && child.signalCode === null) child.kill('SIGTERM');
      if (!await waitForExit(10000)) {
        child.kill('SIGKILL');
        if (!await waitForExit(5000)) throw new Error('Isolated QA editor did not exit after SIGKILL.');
      }
    } catch (error) { failure ||= error; }
    finally { child.unref(); }
    await log.close().catch(error => { failure ||= error; });
  }
  if (failure) throw failure;
  console.log('Native VSIX installation, activation, permanent runtime, connector setup and restart: PASS', result);
})().catch(error => { console.error(error); process.exitCode = 1; });
