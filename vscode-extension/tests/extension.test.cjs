'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const vm = require('node:vm');
const { parseRuntime, discover, copyRuntime, boardHtml, requestJson, needsRuntimeUpgrade } = require('../extension.cjs');

test('Discovery verifies exact instance without sending its expected nonce', async () => {
  const dataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'agentboard-discovery-'));
  let health;
  const requests = [];
  const server = http.createServer((request, response) => {
    requests.push(request.headers);
    response.setHeader('Content-Type', 'application/json');
    response.end(JSON.stringify(health));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const runtime = { schema_version: 1, base_url: `http://127.0.0.1:${server.address().port}`,
    data_dir: dataDir, instance_id: crypto.randomUUID(), mode: 'vscode', version: '1.4.0', pid: process.pid };
  health = { status: 'ok', ...runtime, mcp_running: false };
  await fs.writeFile(path.join(dataDir, 'runtime.json'), JSON.stringify(runtime));
  try {
    assert.equal((await discover(dataDir)).instance_id, runtime.instance_id);
    assert.equal(requests[0]['x-agentboard-instance'], undefined);
    for (const changes of [{ instance_id: crypto.randomUUID() }, { pid: 1 }, { mode: 'desktop' },
      { version: '0.1.0' }, { mcp_running: undefined }, { mcp_running: 'false' }]) {
      health = { status: 'ok', ...runtime, mcp_running: false, ...changes };
      assert.equal(await discover(dataDir), null);
    }
    for (const changes of [{ base_url: 'http://example.com:4242' }, { base_url: 'http://127.0.0.1:99999' },
      { base_url: runtime.base_url + '/path' }, { base_url: runtime.base_url + '?token=secret' },
      { base_url: 'http://user@127.0.0.1:4242' }, { data_dir: path.dirname(dataDir) },
      { instance_id: 'no-proof' }, { pid: -1 }, { mode: 'unknown' }, { version: '01.4.0' }]) {
      assert.throws(() => parseRuntime({ ...runtime, ...changes }, dataDir));
    }
  } finally { await new Promise(resolve => server.close(resolve)); await fs.rm(dataDir, { recursive: true, force: true }); }
});

test('Version lifecycle never stops newer runtimes, desktop or active MCP', () => {
  const runtime = { version: '1.4.0', mode: 'vscode', mcp_running: false };
  assert.equal(needsRuntimeUpgrade(runtime, '1.4.1'), true);
  assert.equal(needsRuntimeUpgrade(runtime, '1.10.0'), true);
  assert.equal(needsRuntimeUpgrade(runtime, '1.3.0'), false);
  assert.equal(needsRuntimeUpgrade(runtime, '1.4.0'), false);
  assert.equal(needsRuntimeUpgrade({ ...runtime, mode: 'desktop' }, '1.5.0'), false);
  assert.equal(needsRuntimeUpgrade({ ...runtime, mcp_running: true }, '1.5.0'), false);
});

test('Concurrent runtime staging retains durable MCP path and personal data', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'agentboard-copy-'));
  const extension = path.join(directory, 'extension');
  const data = path.join(directory, 'data');
  const bundle = path.join(extension, 'runtime', 'Agentboard');
  await fs.mkdir(path.join(bundle, '_internal'), { recursive: true });
  await fs.mkdir(data);
  await fs.writeFile(path.join(bundle, '_internal', 'package.json'), JSON.stringify({ version: '1.4.0' }));
  await fs.writeFile(path.join(bundle, 'AgentboardMCP.exe'), 'fixture');
  await fs.writeFile(path.join(data, 'agentboard.sqlite3'), 'personal data fixture');
  try {
    const [first, second] = await Promise.all([copyRuntime(extension, data, '1.4.0'), copyRuntime(extension, data, '1.4.0')]);
    assert.equal(first, second);
    assert.deepEqual(await fs.readdir(path.join(data, 'vscode-runtime')), ['1.4.0']);
    await fs.rename(extension, path.join(directory, 'removed-extension'));
    assert.equal(await fs.readFile(path.join(first, 'AgentboardMCP.exe'), 'utf8'), 'fixture');
    assert.equal(await fs.readFile(path.join(data, 'agentboard.sqlite3'), 'utf8'), 'personal data fixture');
  } finally { await fs.rm(directory, { recursive: true, force: true }); }
});

test('Webview confines resources and messages to the validated runtime frame', () => {
  const html = boardHtml({ base_url: 'http://127.0.0.1:4243' });
  assert.match(html, /default-src 'none'; frame-src http:\/\/127\.0\.0\.1:4243/);
  assert.match(html, /event.source === frame.contentWindow && event.origin === origin/);
  assert.match(html, /nonce="[a-f0-9]{48}"/);
  assert.doesNotMatch(html, /unsafe-inline|unsafe-eval|file:\/\/|https:\/\//);
});

test('Webview bridge accepts the preload reply when VS Code masks window.parent', () => {
  const origin = 'http://127.0.0.1:4243';
  const preloadOrigin = 'vscode-webview://' + 'a'.repeat(52);
  const sent = [], replies = [];
  const child = { postMessage: (...value) => replies.push(value) };
  const window = { location: { origin: preloadOrigin }, addEventListener: (_kind, listener) => { window.receive = listener; } };
  window.parent = window; // Microsoft's preload replaces window.parent before extension HTML runs.
  const script = boardHtml({ base_url: origin }).match(/<script nonce="[a-f0-9]+">([\s\S]*?)<\/script>/)[1];
  vm.runInNewContext(script, { window, document: { getElementById: () => ({ contentWindow: child }) },
    acquireVsCodeApi: () => ({ postMessage: value => sent.push(value) }) });
  const request = { kind: 'agentboard-host', id: 'one', action: 'clipboard', text: 'test' };
  window.receive({ source: child, origin, data: request });
  window.receive({ source: child, origin: 'https://example.com', data: request });
  window.receive({ source: {}, origin, data: request });
  assert.deepEqual(sent, [request]);
  const reply = { kind: 'agentboard-host-result', id: 'one', result: true };
  window.receive({ source: {}, origin: preloadOrigin, data: reply });
  window.receive({ source: child, origin, data: reply });
  window.receive({ source: {}, origin: 'https://example.com', data: reply });
  assert.deepEqual(replies, [[reply, origin]]);
});

test('Local JSON transport rejects redirects and oversized responses', async () => {
  const server = http.createServer((request, response) => {
    if (request.url === '/redirect') { response.writeHead(302, { Location: 'http://example.com/' }); response.end('{}'); }
    else response.end(JSON.stringify({ body: 'x'.repeat(2048) }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    await assert.rejects(requestJson(base + '/redirect'));
    await assert.rejects(requestJson(base + '/large', 'GET', {}, 100));
  } finally { await new Promise(resolve => server.close(resolve)); }
});
