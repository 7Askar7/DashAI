'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');
const { verifyManifest, checkUpdate, downloadUpdate, activateUpdates } = require('../updates.cjs');

// Node 20 exposes fetch through a lazy getter; node:test mock.method needs a value descriptor.
Object.defineProperty(globalThis, 'fetch', { value: globalThis.fetch, writable: true, configurable: true });

const key = crypto.generateKeyPairSync('ed25519');
const publicKey = key.publicKey.export({ format: 'der', type: 'spki' }).subarray(-32).toString('base64');
const bytes = Buffer.from('verified VSIX fixture');
const asset = 'https://github.com/7Askar7/DashAI/releases/download/v1.4.0/Agentboard-VSCode-1.4.0-win32-x64.vsix';
const config = {
  manifest_url: 'https://github.com/7Askar7/DashAI/releases/latest/download/vscode-latest.json',
  public_key: publicKey,
};
const payload = {
  schema_version: 1, version: '1.4.0', target: 'win32-x64', vsix_url: asset,
  size: bytes.length, sha256: crypto.createHash('sha256').update(bytes).digest('hex'),
  published_at: '2026-10-04T10:00:00.123456+00:00',
};

function signed(data = payload) {
  const message = Buffer.from(JSON.stringify(data));
  return { payload: message.toString('base64'), signature: crypto.sign(null, message, key.privateKey).toString('base64') };
}

function streamResponse(chunks) {
  return new Response(new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(new Uint8Array(chunk));
      controller.close();
    },
  }));
}

test('publisher signature, exact schema and numeric newer version are required', () => {
  assert.deepEqual(verifyManifest(signed(), publicKey, '1.3.0'), payload);
  assert.equal(verifyManifest(JSON.stringify(signed()), publicKey, '1.4.0'), null);
  assert.equal(verifyManifest(Buffer.from(JSON.stringify(signed())), publicKey, '2.0.0'), null);
  assert.equal(verifyManifest(signed(), publicKey, '1.10.0'), null);
  const altered = signed();
  altered.payload = Buffer.from(JSON.stringify({ ...payload, size: 1 })).toString('base64');
  assert.throws(() => verifyManifest(altered, publicKey, '1.3.0'), /signature/);
  const foreignKey = crypto.generateKeyPairSync('ed25519').publicKey.export({ format: 'der', type: 'spki' }).subarray(-32).toString('base64');
  assert.throws(() => verifyManifest(signed(), foreignKey, '1.3.0'), /signature/);
  assert.throws(() => verifyManifest({ ...signed(), unsigned: true }, publicKey, '1.3.0'), /manifest/);
  assert.throws(() => verifyManifest({ ...signed(), payload: signed().payload + '\n' }, publicKey, '1.3.0'), /encoding/);
  assert.throws(() => verifyManifest({ ...signed(), signature: 'AA==' }, publicKey, '1.3.0'), /encoding/);
  assert.throws(() => verifyManifest(signed(), '', '1.3.0'), /encoding/);
  assert.throws(() => verifyManifest(signed(), publicKey, '01.3.0'), /version/);
  assert.throws(() => verifyManifest('x'.repeat(256 * 1024 + 1), publicKey, '1.3.0'), /large/);

  for (const changes of [
    { schema_version: true }, { target: 'linux-x64' }, { version: '1.4.0-preview' },
    { version: '65536.0.0' }, { size: 0 }, { size: 128 * 1024 * 1024 + 1 }, { size: 1.5 },
    { sha256: 'A'.repeat(64) }, { published_at: '2026-10-04' }, { published_at: 'invalid' },
    { vsix_url: asset.replace('https:', 'http:') },
    { vsix_url: asset.replace('github.com/', 'github.com.evil.invalid/') },
    { vsix_url: asset.replace('7Askar7', 'another-owner') },
    { vsix_url: asset.replace('v1.4.0/', 'v1.3.0/') },
    { vsix_url: asset + '?download=1' }, { vsix_url: asset + '#fragment' },
    { vsix_url: asset.replace('github.com/', 'token@github.com/') },
  ]) {
    assert.throws(() => verifyManifest(signed({ ...payload, ...changes }), publicKey, '1.3.0'));
  }
  const { size, ...missing } = payload;
  assert.throws(() => verifyManifest(signed(missing), publicKey, '1.3.0'), /format/);
});

test('HTTPS redirects retain only public headers; unsigned feeds and downgrade redirects fail closed', async t => {
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push({ url, options });
    if (requests.length === 1) return new Response(null, { status: 302, headers: { location: 'https://release-assets.githubusercontent.com/public-manifest' } });
    return new Response(JSON.stringify(signed()));
  });
  assert.deepEqual(await checkUpdate(config, '1.3.0'), payload);
  assert.equal(requests.length, 2);
  for (const { options } of requests) {
    assert.equal(options.redirect, 'manual');
    assert.equal(options.credentials, 'omit');
    assert.deepEqual(Object.keys(options.headers).sort(), ['Cache-Control', 'User-Agent']);
  }
  await assert.rejects(checkUpdate({ ...config, manifest_url: 'http://github.com/latest.json' }, '1.3.0'), /channel/);
  await assert.rejects(checkUpdate({ ...config, public_key: null }, '1.3.0'), /encoding/);
  t.mock.method(globalThis, 'fetch', async () => new Response(null, { status: 302, headers: { location: 'http://github.com/unsigned.json' } }));
  await assert.rejects(checkUpdate(config, '1.3.0'), /HTTPS/);
  t.mock.method(globalThis, 'fetch', async () => new Response(null, { status: 302, headers: { location: '/still-redirecting' } }));
  await assert.rejects(checkUpdate(config, '1.3.0'), /redirects/);
});

test('manifest streaming and declared response lengths are bounded', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('oversized', { headers: { 'content-length': String(256 * 1024 + 1) } }));
  await assert.rejects(checkUpdate(config, '1.3.0'), /size/);
  t.mock.method(globalThis, 'fetch', async () => streamResponse([Buffer.alloc(128 * 1024), Buffer.alloc(128 * 1024 + 1)]));
  await assert.rejects(checkUpdate(config, '1.3.0'), /large/);
  t.mock.method(globalThis, 'fetch', async () => new Response('not found', { status: 404 }));
  await assert.rejects(checkUpdate(config, '1.3.0'), /failed/);
});

test('VSIX streaming verifies exact signed bytes and removes failed partial files', async t => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'agentboard-update-test-'));
  t.after(async () => { await fs.rm(directory, { recursive: true, force: true }); });
  t.mock.method(globalThis, 'fetch', async () => streamResponse([bytes.subarray(0, 5), bytes.subarray(5)]));
  const downloaded = await downloadUpdate(verifyManifest(signed(), publicKey, '1.3.0'), directory);
  assert.equal(path.isAbsolute(downloaded), true);
  assert.deepEqual(await fs.readFile(downloaded), bytes);
  const originalDirectories = await fs.readdir(directory);

  for (const corrupt of [Buffer.concat([bytes, Buffer.from('x')]), bytes.subarray(1), Buffer.alloc(bytes.length)]) {
    t.mock.method(globalThis, 'fetch', async () => streamResponse([corrupt]));
    await assert.rejects(downloadUpdate(payload, directory), /size|checksum/);
    assert.deepEqual(await fs.readdir(directory), originalDirectories);
  }
  t.mock.method(globalThis, 'fetch', async () => new Response(bytes, { headers: { 'content-length': String(bytes.length + 1) } }));
  await assert.rejects(downloadUpdate(payload, directory), /size/);
  assert.deepEqual(await fs.readdir(directory), originalDirectories);
});

test('packaged VS Code release key matches the existing trusted desktop publisher', async () => {
  const trustedKey = (await fs.readFile(path.join(__dirname, '../../packaging/update-public-key.txt'), 'utf8')).trim();
  const extensionChannel = JSON.parse(await fs.readFile(path.join(__dirname, '../update-channel.json'), 'utf8'));
  assert.equal(extensionChannel.public_key, trustedKey);
  assert.equal(extensionChannel.manifest_url, config.manifest_url);
});

test('GitHub build wires the manual update command; failures are logged and reported, never thrown', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'agentboard-wiring-'));
  await fs.writeFile(path.join(directory, 'update-channel.json'), JSON.stringify({ ...config, manifest_url: 'https://example.com/feed.json' }));
  const commands = {}, logged = [], failed = [], subscriptions = [];
  const vscode = {
    commands: { registerCommand: (name, action) => { commands[name] = action; return { dispose() {} }; } },
    workspace: { getConfiguration: () => ({ get: () => false }) },
  };
  try {
    activateUpdates({ vscode, context: { extensionPath: directory, subscriptions }, version: '1.4.0', dataDir: directory,
      output: { appendLine: line => logged.push(line) }, fail: error => failed.push(error.message) });
    assert.deepEqual(Object.keys(commands), ['agentboard.checkUpdates']);
    await commands['agentboard.checkUpdates']();
    assert.deepEqual(failed, ['Invalid VS Code update channel']);
    assert.match(logged[0], /Invalid VS Code update channel/);
  } finally {
    subscriptions.forEach(item => item.dispose());
    await fs.rm(directory, { recursive: true, force: true });
  }
});
