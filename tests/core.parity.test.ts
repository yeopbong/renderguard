import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';
import { encode } from 'fast-png';
import { decodePNG } from '../core/png.ts';
import { analyzePair, tensorsForCandidate } from '../core/index.ts';
import { resolve } from 'node:path';

test('Node and browser share exact PNG decode, candidate geometry, and all branch tensors', async () => {
  const fixtures: { name: string; bytes: Uint8Array }[] = [];
  for (const channels of [1, 2, 3, 4]) for (const depth of [8, 16] as const) {
    const width = 21, height = 13, data = depth === 16 ? new Uint16Array(width * height * channels) : new Uint8Array(width * height * channels);
    for (let i = 0; i < data.length; i++) data[i] = (i * 977 + 13) % (depth === 16 ? 65536 : 256);
    fixtures.push({ name: `channels${channels}-depth${depth}`, bytes: encode({ width, height, channels, depth, data }) });
  }
  const palette = [[255, 0, 0, 255], [0, 128, 200, 96], [55, 66, 77, 0], [255, 255, 255, 255]];
  fixtures.push({ name: 'palette2', bytes: encode({ width: 8, height: 3, channels: 1, depth: 2, data: new Uint8Array([27, 228, 177, 78, 27, 228]), palette }) });
  const server = await createServer({ root: resolve('.'), configFile: false, logLevel: 'error', server: { host: '127.0.0.1', port: 0 }, optimizeDeps: { include: ['fast-png'] } });
  await server.listen();
  const address = server.httpServer!.address(); if (!address || typeof address === 'string') throw new Error('Parity server address unavailable.');
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage(); await page.goto(`http://127.0.0.1:${address.port}/core/index.ts`);
    for (const fixture of fixtures) {
      const node = decodePNG(fixture.bytes), reference = PNG.sync.read(Buffer.from(fixture.bytes));
      assert.deepEqual(Array.from(node.data), Array.from(reference.data), `${fixture.name}: independent PNG decoder pixel parity`);
      const browserResult = await page.evaluate(async payload => {
        const modulePath = '/core/png.ts', shared = await import(modulePath);
        const raster = shared.decodePNG(new Uint8Array(payload)); return { width: raster.width, height: raster.height, data: Array.from(raster.data) };
      }, Array.from(fixture.bytes));
      assert.deepEqual(browserResult, { width: node.width, height: node.height, data: Array.from(node.data) }, `${fixture.name}: browser PNG pixel parity`);
    }
    const beforeBytes = fixtures.find(f => f.name === 'channels4-depth8')!.bytes;
    const original = decodePNG(beforeBytes), edited = { ...original, data: new Uint8Array(original.data) };
    for (let y = 4; y < 7; y++) for (let x = 8; x < 11; x++) { edited.data[(y * edited.width + x) * 4] = 0; edited.data[(y * edited.width + x) * 4 + 3] = 255; }
    const afterBytes = encode({ width: edited.width, height: edited.height, channels: 4, depth: 8, data: edited.data }), analysis = analyzePair(original, edited), tensors = analysis.candidates.map(c => Object.fromEntries(Object.entries(tensorsForCandidate(original, edited, c)).map(([key, tensor]) => [key, Array.from(tensor)])));
    const browserResult = await page.evaluate(async payload => {
      const pngPath = '/core/png.ts', corePath = '/core/index.ts', { decodePNG } = await import(pngPath), { analyzePair, tensorsForCandidate } = await import(corePath);
      const before = decodePNG(new Uint8Array(payload.before)), after = decodePNG(new Uint8Array(payload.after)), analysis = analyzePair(before, after);
      return { analysis, tensors: analysis.candidates.map((candidate: any) => Object.fromEntries(Object.entries(tensorsForCandidate(before, after, candidate)).map(([key, tensor]) => [key, Array.from(tensor as Float32Array)]))) };
    }, { before: Array.from(beforeBytes), after: Array.from(afterBytes) });
    assert.deepEqual(browserResult.analysis, analysis); assert.deepEqual(browserResult.tensors, tensors);
  } finally { await browser.close(); await server.close(); }
});
