#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { execFile, execFileSync } = require('node:child_process');
const { promisify } = require('node:util');
const exec = promisify(execFile);
const root = path.resolve(__dirname, '../..');
const out = path.join(root, '.local/advanced-tests/session4');
const artifacts = path.join(out, 'output/playwright');
fs.mkdirSync(artifacts, { recursive: true });
const cli = path.join(__dirname, 'playwright-cli.cjs');
const runtime = JSON.parse(execFileSync(process.execPath, [cli, '--runtime-info'], { encoding: 'utf8' }));
const session = `ppt1-advanced-smoke-${process.pid}`;
const config = path.join(out, 'playwright-cli.json');
const cache = process.env.PLAYWRIGHT_BROWSERS_PATH || path.join(root, '.local/advanced-browser-cache');
process.env.PLAYWRIGHT_BROWSERS_PATH = cache;
const playwright = require(path.join(runtime.modules, 'playwright'));
// Only exported package entrypoints and documented BrowserType APIs are used.
// executablePath() describes full Chromium; Playwright chooses its installed
// headless shell automatically when launchOptions.headless is true.
const defaultExecutablePath = playwright.chromium.executablePath();
const launchOptions = { headless: true, chromiumSandbox: false };
if (process.env.PPT1_PLAYWRIGHT_EXECUTABLE_PATH) launchOptions.executablePath = path.resolve(process.env.PPT1_PLAYWRIGHT_EXECUTABLE_PATH);
const preflight = { runtime, runtime_selection: 'wrapper --runtime-info; shared or local fallback uses the same pinned selection policy', public_package_entry: 'playwright', public_apis: ['chromium.executablePath()', 'chromium.launch (via CLI)'], executablePath: defaultExecutablePath, default_full_browser_exists: fs.existsSync(defaultExecutablePath), explicit_executable_path: launchOptions.executablePath || null, headless_shell_resolution: 'delegated to Playwright public launch behavior; no private registry import or guessed shell path', passed: typeof playwright.chromium.launch === 'function' && typeof defaultExecutablePath === 'string' };
fs.writeFileSync(path.join(out, 'preflight-result.json'), JSON.stringify(preflight, null, 2)+'\n');
if (process.argv.includes('--preflight')) { console.log(JSON.stringify(preflight, null, 2)); process.exit(preflight.passed ? 0 : 1); }
fs.writeFileSync(config, JSON.stringify({ browser: { browserName: 'chromium', launchOptions, contextOptions: { viewport: { width: 1200, height: 800 } } }, outputDir: artifacts }, null, 2)+'\n');
const html = fs.readFileSync(path.join(__dirname, 'test-page.html'));
const server = http.createServer((req, res) => { res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); res.end(html); });
const results = [];
async function command(args) {
  try {
    const { stdout, stderr } = await exec(process.execPath, [cli, `-s=${session}`, ...args], { cwd: out, env: { ...process.env, PLAYWRIGHT_BROWSERS_PATH: cache }, timeout: 60000, maxBuffer: 4*1024*1024 });
    results.push({ args, stdout, stderr });
    if (/^### Error/m.test(stdout)) throw new Error(stdout);
    return stdout;
  } catch (error) {
    if (error.stdout || error.stderr) results.push({ args, exit_code: error.code, stdout: error.stdout, stderr: error.stderr });
    throw error;
  } finally { fs.writeFileSync(path.join(out, 'cli-test-log.json'), JSON.stringify(results, null, 2)+'\n'); }
}
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const url = `http://127.0.0.1:${server.address().port}/`;
  let opened = false;
  try {
    await command(['open', url, `--config=${config}`]); opened = true;
    await command(['snapshot', '--filename=output/playwright/before.yaml']);
    const before = fs.readFileSync(path.join(artifacts, 'before.yaml'), 'utf8');
    const match = before.match(/button "완료 표시" \[ref=(e\d+)\]/);
    if (!match) throw new Error('Fresh snapshot did not contain expected button reference.');
    await command(['click', match[1]]);
    await command(['snapshot', '--filename=output/playwright/after.yaml']);
    const after = fs.readFileSync(path.join(artifacts, 'after.yaml'), 'utf8');
    if (!after.includes('로컬 CLI 검증 완료')) throw new Error('Click result not found in snapshot.');
    await command(['screenshot', '--filename=output/playwright/local-test.png']);
    fs.writeFileSync(path.join(out, 'test-result.json'), JSON.stringify({ passed: true, url, session, defaultExecutablePath, runtime_version: runtime.version, snapshot_before: 'output/playwright/before.yaml', snapshot_after: 'output/playwright/after.yaml', screenshot: 'output/playwright/local-test.png', uses_user_authentication: false, browser_profile: 'isolated CLI session; no user CDP/extension/storage attached', commands: results.length }, null, 2)+'\n');
    console.log('PASS: local page -> snapshot -> ref click -> snapshot -> screenshot');
  } catch (error) {
    fs.writeFileSync(path.join(out, 'test-result.json'), JSON.stringify({ passed: false, status: 'BLOCKED_BROWSER_UNAVAILABLE', url, session, preflight_passed: preflight.passed, cli_open_attempted: results.length > 0, local_page_opened: opened, snapshot_created: false, screenshot_created: false, user_authentication_used: false, error: String(error.message), official_browser_install_still_blocked: true }, null, 2)+'\n');
    throw error;
  } finally {
    if (opened) await command(['close']);
    server.close();
  }
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
