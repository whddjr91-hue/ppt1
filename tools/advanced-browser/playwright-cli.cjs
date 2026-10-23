#!/usr/bin/env node
// Local adapter. Upstream vendor files remain unmodified.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const lock = JSON.parse(fs.readFileSync(path.join(__dirname, 'runtime-lock.json'), 'utf8'));
const candidates = [process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, path.join(__dirname, 'node_modules')].filter(Boolean);
let runtime;
for (const modules of candidates) {
  const pkg = path.join(modules, 'playwright/package.json');
  if (!fs.existsSync(pkg)) continue;
  const data = JSON.parse(fs.readFileSync(pkg, 'utf8'));
  const cli = path.join(modules, 'playwright/cli.js');
  const sha256 = crypto.createHash('sha256').update(fs.readFileSync(cli)).digest('hex');
  if (data.version === lock.playwright_version && sha256 === lock.cli_sha256) {
    runtime = { modules, cli, version: data.version, cli_sha256: sha256 };
    break;
  }
}
if (!runtime) {
  console.error(`Pinned Playwright ${lock.playwright_version} runtime was not found. No automatic npm/global install was attempted.`);
  process.exit(2);
}
const env = { ...process.env, PLAYWRIGHT_BROWSERS_PATH: process.env.PLAYWRIGHT_BROWSERS_PATH || path.join(root, '.local/advanced-browser-cache'), XDG_CACHE_HOME: path.join(root, '.local/advanced-browser-cache/cli-state') };
let args = process.argv.slice(2);
if (args[0] === '--runtime-info') {
  console.log(JSON.stringify({ ...runtime, browser_cache: env.PLAYWRIGHT_BROWSERS_PATH }, null, 2));
  process.exit(0);
}
if (args[0] === '--install-browser') {
  args = ['install', 'chromium', '--only-shell'];
} else {
  if (process.env.PLAYWRIGHT_CLI_SESSION && !args.some(a => a === '--session' || a.startsWith('--session=') || a.startsWith('-s='))) {
    args.unshift(`-s=${process.env.PLAYWRIGHT_CLI_SESSION}`);
  }
  args.unshift('cli');
}
const result = spawnSync(process.execPath, [runtime.cli, ...args], { env, stdio: 'inherit' });
if (result.error) console.error(result.error.message);
process.exit(result.status === null ? 1 : result.status);
