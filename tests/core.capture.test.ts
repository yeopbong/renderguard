import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer, type Server } from 'node:http';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { capturePair, type CaptureConfig } from '../capture/run.ts';
import { readPng } from '../capture/png.ts';
import { analyzePair, tensorsForCandidate } from '../core/index.ts';
let server: Server, origin: string, directory: string;
const fixture = (moved: boolean) => `<!doctype html><html lang="en"><meta charset="utf-8"><style>html,body{margin:0;background:#fff;color:#111;font:16px sans-serif}.page{padding:24px;height:1300px}.container{width:300px;height:160px;border:2px solid #234;position:relative}.button{position:absolute;left:${moved ? 240 : 20}px;top:35px;width:110px;height:40px;background:#247;color:white}.neighbor{position:absolute;left:260px;top:30px;width:45px;height:60px;border:1px solid #b51}#tail{margin-top:1000px;width:30px;height:20px;background:#195}</style><div class="page" data-ready="true"><div class="container"><button class="button">Continue</button><div class="neighbor"></div></div><div id="tail"></div></div></html>`;
test.before(async () => {
  directory = await mkdtemp(join(tmpdir(), 'renderguard-capture-'));
  server = createServer((request, response) => {
    if (request.url === '/redirect') { response.writeHead(302, { Location: 'http://example.invalid/blocked' }).end(); return; }
    response.setHeader('Content-Type', 'text/html');
    if (request.url === '/external') { response.end('<!doctype html><img src="http://example.invalid/image.png">'); return; }
    if (request.url === '/dynamic') { response.end('<!doctype html><style>body{margin:0}#clock{width:100px;height:80px;background:red}</style><div id="clock"></div><script>let x=0;setInterval(()=>{document.querySelector("#clock").style.width=(100+(x++%100))+"px"},1)</script>'); return; }
    response.end(fixture(request.url === '/after'));
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve)); const address = server.address(); if (!address || typeof address === 'string') throw new Error('Fixture address unavailable.'); origin = `http://127.0.0.1:${address.port}`;
});
test.after(async () => { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); await rm(directory, { recursive: true, force: true }); });
const configuration = (name: string): CaptureConfig => ({ beforeUrl: `${origin}/before`, afterUrl: `${origin}/after`, outputDir: join(directory, name), viewport: { width: 480, height: 640 }, readySelector: '[data-ready]', deviceScaleFactor: 2, state: { fixedTime: 1700000000000, randomSeed: 1 }, contracts: [{ type: 'required-visible', selector: '.button' }, { type: 'inside-container', selector: '.button', container: '.container' }, { type: 'non-overlap', selector: '.button', other: '.neighbor' }, { type: 'required-visible', selector: '.missing' }] });
test('real Chromium captures CSS-scale high-DPR long pages and concrete contracts', async () => {
  const result = await capturePair(configuration('primary')) as any;
  assert.equal(result.execution, 'complete'); assert.equal(result.before.deviceScaleFactor, 2); assert.equal(result.before.actualDevicePixelRatio, 2); assert.equal(result.before.cssToImageScale, 1); assert.equal(result.before.imageSize.width, 480); assert.ok(result.before.imageSize.height > 1300); assert.equal(result.before.stableUnderMasks, true);
  assert.deepEqual(result.contracts.map((c: any) => c.status), ['satisfied', 'violated', 'violated', 'inconclusive']); assert.equal(result.contracts[1].before.status, 'satisfied');
  assert.equal(result.contracts[1].measurements[0].box.x, 266); assert.equal(result.manifestPath, 'manifest.json');
  const [a, b] = await Promise.all([readPng(join(directory, 'primary', 'before.png')), readPng(join(directory, 'primary', 'after.png'))]); const analysis = analyzePair(a, b); assert.ok(analysis.candidates.length > 0); assert.ok(analysis.changedPixels > 0);
  assert.ok((await readFile(join(directory, 'primary', 'diff.png'))).byteLength > 0);
});
test('same visual pair with different declared constraints preserves candidate tensors', async () => {
  const config = configuration('different-contracts'); config.contracts = [{ type: 'inside-container', selector: '.button', container: '.page' }];
  const result = await capturePair(config) as any; assert.equal(result.contracts[0].status, 'satisfied');
  const [a, b, previousA, previousB] = await Promise.all([readPng(join(config.outputDir, 'before.png')), readPng(join(config.outputDir, 'after.png')), readPng(join(directory, 'primary', 'before.png')), readPng(join(directory, 'primary', 'after.png'))]);
  const analysis = analyzePair(a, b), previous = analyzePair(previousA, previousB); assert.deepEqual(analysis, previous); for (let i = 0; i < analysis.candidates.length; i++) assert.deepEqual(tensorsForCandidate(a, b, analysis.candidates[i]), tensorsForCandidate(previousA, previousB, previous.candidates[i]));
});
test('normal repeated capture produces zero visual candidates', async () => {
  const config = configuration('unchanged'); config.afterUrl = config.beforeUrl; config.contracts = [];
  const result = await capturePair(config) as any; assert.equal(result.execution, 'complete'); assert.equal(result.before.sha256, result.after.sha256);
  assert.equal(analyzePair(await readPng(join(config.outputDir, 'before.png')), await readPng(join(config.outputDir, 'after.png'))).changedPixels, 0);
});
test('off-allowlist redirects and subresources fail instead of returning no-change', async () => {
  for (const path of ['/redirect', '/external']) {
    const config = configuration(path.slice(1)); config.beforeUrl = `${origin}${path}`; config.readySelector = undefined; config.timeoutMs = 3000;
    await assert.rejects(capturePair(config)); const failure = JSON.parse(await readFile(join(config.outputDir, 'failure.json'), 'utf8')); assert.equal(failure.execution, 'error'); assert.match(failure.stage, /^before:/);
  }
});
test('user mask makes explicitly bounded dynamic content comparable', async () => {
  const config = configuration('masked-dynamic'); config.beforeUrl = config.afterUrl = `${origin}/dynamic`; config.readySelector = '#clock'; config.contracts = []; config.masks = [{ x: 0, y: 0, width: 210, height: 90, source: 'User declared animated panel' }];
  const result = await capturePair(config) as any; assert.equal(result.execution, 'complete'); assert.equal(result.before.stableUnderMasks, true); assert.deepEqual(result.masks, config.masks);
  assert.equal(analyzePair(await readPng(join(config.outputDir, 'before.png')), await readPng(join(config.outputDir, 'after.png')), config.masks).changedPixels, 0);
});
