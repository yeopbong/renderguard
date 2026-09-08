import test from 'node:test';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { decodePNG } from '../core/png.ts';

test('fullPage plus document clip retains the tail that clip alone truncates at the viewport', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 480, height: 600 }, deviceScaleFactor: 1 });
    await page.setContent('<!doctype html><style>html,body{margin:0}main{height:2300px;background:#fff;position:relative}footer{position:absolute;bottom:0;height:80px;width:100%;background:#c92739}</style><main><p>Long document fixture</p><footer></footer></main>');
    const bounds = await page.evaluate(() => ({ x: 0, y: 0, width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight }));
    assert.ok(bounds.height > 2000);
    const truncated = decodePNG(await page.screenshot({ clip: bounds, scale: 'css' }));
    const complete = decodePNG(await page.screenshot({ clip: bounds, fullPage: true, scale: 'css' }));
    assert.equal(truncated.height, 600, 'The historical clip-only path reproduces the lost-tail bug.');
    assert.equal(complete.height, bounds.height, 'The corrected path must preserve actual document scrollHeight.');
    assert.equal(complete.width, bounds.width);
    const tail = ((complete.height - 20) * complete.width + 20) * 4;
    assert.deepEqual(Array.from(complete.data.slice(tail, tail + 4)), [201, 39, 57, 255]);
  } finally { await browser.close(); }
});
