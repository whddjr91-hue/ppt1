#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { launch, installedChromium } = require('./chromium-runtime.cjs');
const out = path.resolve(__dirname, '../../.local/advanced-tests/session4/api');
fs.mkdirSync(out, { recursive: true });
const server = http.createServer((req, res) => { res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); res.end(fs.readFileSync(path.join(__dirname, 'test-page.html'))); });
(async () => {
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  let browser;
  try {
    const launched = await launch(); browser = launched.browser;
    const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    fs.writeFileSync(path.join(out, 'before.yaml'), await page.locator('body').ariaSnapshot());
    await page.getByRole('button', { name: '완료 표시', exact: true }).click();
    const after = await page.locator('body').ariaSnapshot();
    if (!after.includes('로컬 CLI 검증 완료')) throw new Error('Button click did not update page');
    fs.writeFileSync(path.join(out, 'after.yaml'), after);
    await page.screenshot({ path: path.join(out, 'local-test.png'), fullPage: true });
    installedChromium();
    fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ passed: true, browser: launched.receipt.version, playwright: launched.runtime.version, transport: 'public API stdio', pageOpened: true, buttonClicked: true, snapshotCreated: true, screenshotCreated: true, executableIntegrityAfterTest: true, userAuthenticationUsed: false, externalSitesTested: false }, null, 2) + '\n');
    console.log('PASS: localhost page → snapshot → button click → snapshot → PNG; executable integrity retained');
  } catch (error) {
    fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ passed: false, error: error.message }, null, 2)); throw error;
  } finally { if (browser) await browser.close(); server.close(); }
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
