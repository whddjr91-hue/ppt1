#!/usr/bin/env node
// Install only the verified npm distribution into a project-owned cache.
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { createRequire } = require('node:module');
const { createBrotliDecompress } = require('node:zlib');
const { pipeline } = require('node:stream/promises');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const cache = path.join(root, '.local/advanced-browser-cache');
const receiptPath = path.join(cache, 'chromium-install.json');
const packageRoot = path.join(__dirname, 'chromium');
const req = createRequire(path.join(packageRoot, 'package.json'));
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const expectedHash = '53a15d6c3a3d27dfb54c4ba60278b1683136f70cf1e67e989da7dfbd3d451ef0';

(async () => {
  if (process.platform !== 'linux' || process.arch !== 'x64') throw new Error('This optional distribution is Linux x64 only. Use the official Playwright installer on other platforms.');
  const lock = JSON.parse(fs.readFileSync(path.join(packageRoot, 'package-lock.json'), 'utf8'));
  const pinned = lock.packages['node_modules/@sparticuz/chromium'];
  const packageDir = path.join(packageRoot, 'node_modules/@sparticuz/chromium');
  const pkg = JSON.parse(fs.readFileSync(path.join(packageDir, 'package.json'), 'utf8'));
  if (pkg.version !== '153.0.0' || pinned.version !== pkg.version || !pinned.integrity.startsWith('sha512-')) throw new Error('Pinned distribution mismatch');
  if (fs.existsSync(receiptPath)) {
    const old = JSON.parse(fs.readFileSync(receiptPath, 'utf8'));
    const binaryBase = path.join(packageRoot, 'node_modules/.cache/ppt1-chromium') + path.sep;
    if (old.packageVersion === pkg.version && old.npmIntegrity === pinned.integrity && old.executablePath.startsWith(binaryBase) && fs.existsSync(old.executablePath) && fs.statSync(old.executablePath).size === 209022176 && hash(old.executablePath) === expectedHash) {
      console.log(JSON.stringify({ ...old, reused: true }, null, 2)); return;
    }
  }
  await fsp.mkdir(cache, { recursive: true });
  // Keep large generated runtime files with npm dependencies, outside source syncing.
  const binaryCache = path.join(packageRoot, 'node_modules/.cache/ppt1-chromium');
  await fsp.mkdir(binaryCache, { recursive: true });
  const directory = await fsp.mkdtemp(path.join(binaryCache, `chromium-${pkg.version}-`));
  const bin = path.join(packageDir, 'bin');
  const tar = req('tar-fs');
  const assets = {};
  try {
    for (const file of ['chromium.br', 'fonts.tar.br', 'swiftshader.tar.br']) {
      const input = path.join(bin, file); assets[file] = hash(input);
      const output = file === 'chromium.br'
        ? fs.createWriteStream(path.join(directory, 'chromium'), { mode: 0o700 })
        : tar.extract(file === 'fonts.tar.br' ? path.join(directory, 'fonts') : directory, { chown: false });
      // Preserve current ownership: this workspace does not implement chown.
      // tar-fs path/symlink validation and regular permission filtering remain active.
      await pipeline(fs.createReadStream(input), createBrotliDecompress(), output);
    }
    const executablePath = path.join(directory, 'chromium');
    if (fs.statSync(executablePath).size !== 209022176 || hash(executablePath) !== expectedHash) throw new Error('Extracted Chromium integrity mismatch');
    const handle = await fsp.open(executablePath, 'r');
    await handle.sync(); await handle.close();
    await fsp.chmod(executablePath, 0o500);
    const version = execFileSync(executablePath, ['--version'], { encoding: 'utf8', timeout: 15000 }).trim();
    const result = { distribution: '@sparticuz/chromium', packageVersion: pkg.version,
      npmIntegrity: pinned.integrity, executablePath, version, sha256: hash(executablePath),
      bytes: fs.statSync(executablePath).size, directory, assets, platform: process.platform, arch: process.arch,
      extraction: 'Brotli plus tar-fs chown:false; no upstream source modifications',
      playwrightVersion: '1.62.1', compatibility: 'Must pass actual project CLI smoke before ready',
      userAuthenticationUsed: false };
    const temporary = receiptPath + '.pending';
    await fsp.writeFile(temporary, JSON.stringify(result, null, 2) + '\n');
    await fsp.rename(temporary, receiptPath);
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    await fsp.rm(directory, { recursive: true, force: true }); throw error;
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
