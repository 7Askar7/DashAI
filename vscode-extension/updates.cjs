'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');

const MAX_MANIFEST = 256 * 1024;
const MAX_VSIX = 128 * 1024 * 1024;
const FEED = 'https://github.com/7Askar7/DashAI/releases/latest/download/vscode-latest.json';
const PAYLOAD_KEYS = ['published_at', 'schema_version', 'sha256', 'size', 'target', 'version', 'vsix_url'];

function httpsUrl(value) {
  if (typeof value !== 'string' || value.length > 4096) throw new Error('Invalid update URL');
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.username || url.password || url.hash) {
    throw new Error('Updates require HTTPS without credentials or fragments');
  }
  return url;
}

function version(value) {
  if (typeof value !== 'string' || !/^(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})$/.test(value)) {
    throw new Error('Invalid update version');
  }
  const parts = value.split('.').map(Number);
  if (parts.some(part => part > 65535)) throw new Error('Invalid update version');
  return parts;
}

function base64(value, size) {
  if (typeof value !== 'string' || !value.length || value.length % 4) throw new Error('Invalid update encoding');
  const bytes = Buffer.from(value, 'base64');
  if (bytes.toString('base64') !== value || (size !== undefined && bytes.length !== size)) {
    throw new Error('Invalid update encoding');
  }
  return bytes;
}

function validatePayload(payload) {
  if (!payload || Array.isArray(payload) || Object.keys(payload).sort().join(',') !== PAYLOAD_KEYS.join(',') ||
      payload.schema_version !== 1 || payload.target !== 'win32-x64') {
    throw new Error('Unsupported VS Code update format');
  }
  version(payload.version);
  const expected = `https://github.com/7Askar7/DashAI/releases/download/v${payload.version}/Agentboard-VSCode-${payload.version}-win32-x64.vsix`;
  httpsUrl(payload.vsix_url);
  if (payload.vsix_url !== expected) throw new Error('Unexpected VS Code update asset');
  if (!Number.isSafeInteger(payload.size) || payload.size < 1 || payload.size > MAX_VSIX ||
      typeof payload.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(payload.sha256)) {
    throw new Error('Invalid VS Code update size or checksum');
  }
  if (typeof payload.published_at !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(payload.published_at) ||
      !Number.isFinite(Date.parse(payload.published_at))) {
    throw new Error('Invalid VS Code update date');
  }
  return payload;
}

function verifyManifest(envelope, publicKey, currentVersion) {
  if (Buffer.isBuffer(envelope) || typeof envelope === 'string') {
    if (Buffer.byteLength(envelope) > MAX_MANIFEST) throw new Error('Update manifest is too large');
    envelope = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.from(envelope)));
  }
  if (!envelope || Array.isArray(envelope) || Object.keys(envelope).sort().join(',') !== 'payload,signature' ||
      Buffer.byteLength(JSON.stringify(envelope)) > MAX_MANIFEST) {
    throw new Error('Invalid update manifest');
  }
  const payload = base64(envelope.payload);
  const signature = base64(envelope.signature, 64);
  const key = crypto.createPublicKey({
    key: Buffer.concat([Buffer.from('302a300506032b6570032100', 'hex'), base64(publicKey, 32)]),
    format: 'der', type: 'spki',
  });
  if (!crypto.verify(null, payload, key, signature)) throw new Error('Update publisher signature does not match');
  const data = validatePayload(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(payload)));
  const newer = version(data.version);
  const current = version(currentVersion);
  for (let i = 0; i < 3; i += 1) {
    if (newer[i] !== current[i]) return newer[i] > current[i] ? data : null;
  }
  return null;
}

async function request(url, limit) {
  for (let redirects = 0; redirects <= 5; redirects += 1) {
    httpsUrl(url);
    const response = await fetch(url, {
      redirect: 'manual', credentials: 'omit', signal: AbortSignal.timeout(60000),
      headers: { 'User-Agent': 'Agentboard-VSCode-Updater', 'Cache-Control': 'no-cache' },
    });
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      const location = response.headers.get('location');
      await response.body?.cancel();
      if (!location) throw new Error('Update redirect has no destination');
      url = new URL(location, url).href;
      continue;
    }
    const declared = response.headers.get('content-length');
    if (response.status !== 200 || !response.body ||
        (declared !== null && (!/^\d+$/.test(declared) || !Number.isSafeInteger(Number(declared)) || Number(declared) > limit))) {
      await response.body?.cancel();
      throw new Error('Update download failed or exceeds the permitted size');
    }
    return response;
  }
  throw new Error('Too many update redirects');
}

async function checkUpdate(config, currentVersion) {
  // No unsigned or independently configured release channel is accepted.
  if (!config || config.manifest_url !== FEED) throw new Error('Invalid VS Code update channel');
  base64(config.public_key, 32);
  version(currentVersion);
  const response = await request(config.manifest_url, MAX_MANIFEST);
  const chunks = [];
  let size = 0;
  for await (const block of response.body) {
    size += block.length;
    if (size > MAX_MANIFEST) throw new Error('Update manifest is too large');
    chunks.push(Buffer.from(block));
  }
  return verifyManifest(Buffer.concat(chunks), config.public_key, currentVersion);
}

async function downloadUpdate(manifest, directory) {
  validatePayload(manifest);
  await fs.mkdir(directory, { recursive: true });
  const temporaryDirectory = await fs.mkdtemp(path.join(path.resolve(directory), 'Agentboard-update-'));
  const destination = path.join(temporaryDirectory, `Agentboard-VSCode-${manifest.version}-win32-x64.vsix`);
  const temporary = destination + '.part';
  let output;
  try {
    const response = await request(manifest.vsix_url, manifest.size);
    output = await fs.open(temporary, 'wx', 0o600);
    const digest = crypto.createHash('sha256');
    let size = 0;
    for await (const block of response.body) {
      size += block.length;
      if (size > manifest.size) throw new Error('VSIX exceeds its signed size');
      digest.update(block);
      await output.writeFile(block);
    }
    await output.close();
    output = undefined;
    if (size !== manifest.size || digest.digest('hex') !== manifest.sha256) {
      throw new Error('VSIX size or checksum does not match its signed manifest');
    }
    await fs.rename(temporary, destination);
    return destination;
  } catch (error) {
    await output?.close();
    await fs.rm(temporary, { force: true });
    await fs.rmdir(temporaryDirectory);
    throw error;
  }
}

module.exports = { verifyManifest, checkUpdate, downloadUpdate };
