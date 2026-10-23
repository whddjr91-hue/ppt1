#!/usr/bin/env node
const fs = require('node:fs/promises');
const path = require('node:path');
const { launch } = require('./chromium-runtime.cjs');
(async () => {
  const [input, output] = process.argv.slice(2);
  if (!input || !output) throw new Error('Usage: node tools/advanced-browser/capture.cjs https://example.com /absolute/output.png');
  const url = new URL(input);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('An HTTP(S) URL without embedded credentials is required.');
  const destination = path.resolve(output);
  if (!destination.endsWith('.png')) throw new Error('Output must end in .png');
  await fs.mkdir(path.dirname(destination), { recursive: true });
  const { browser, receipt, runtime } = await launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const response = await page.goto(url.href, { waitUntil: 'load', timeout: 45000 });
    if (response && !response.ok()) throw new Error(`Page returned HTTP ${response.status()}`);
    await page.screenshot({ path: destination, fullPage: true });
    await fs.writeFile(destination + '.snapshot.yaml', await page.locator('body').ariaSnapshot());
    await fs.writeFile(destination + '.json', JSON.stringify({ requestedUrl: url.href, finalUrl: page.url(), title: await page.title(), browser: receipt.version, playwright: runtime.version, screenshot: destination, userAuthenticationUsed: false, capturedAt: new Date().toISOString() }, null, 2) + '\n');
    console.log(`Saved: ${destination}`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
