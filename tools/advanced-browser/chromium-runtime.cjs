const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const expected = { bytes: 209022176, sha256: '53a15d6c3a3d27dfb54c4ba60278b1683136f70cf1e67e989da7dfbd3d451ef0' };
function installedChromium() {
  const receipt = JSON.parse(fs.readFileSync(path.join(root, '.local/advanced-browser-cache/chromium-install.json'), 'utf8'));
  const base = fs.realpathSync(path.join(__dirname, 'chromium/node_modules/.cache/ppt1-chromium')) + path.sep;
  const executablePath = fs.realpathSync(receipt.executablePath);
  if (!executablePath.startsWith(base) || fs.statSync(executablePath).size !== expected.bytes || crypto.createHash('sha256').update(fs.readFileSync(executablePath)).digest('hex') !== expected.sha256) throw new Error('Chromium integrity check failed. Run prepare-chromium.cjs to repair it.');
  return { ...receipt, executablePath };
}
async function launch() {
  const receipt = installedChromium();
  const runtime = JSON.parse(execFileSync(process.execPath, [path.join(__dirname, 'playwright-cli.cjs'), '--runtime-info'], { encoding: 'utf8' }));
  const playwright = require(path.join(runtime.modules, 'playwright'));
  // Public API uses stdio transport; no CLI daemon or Unix socket is needed.
  const browser = await playwright.chromium.launch({ executablePath: receipt.executablePath, headless: true, chromiumSandbox: process.getuid?.() !== 0 });
  return { browser, receipt, runtime };
}
module.exports = { installedChromium, launch };
