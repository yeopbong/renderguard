
import { createServer } from 'node:http';
import { readFile, mkdir } from 'node:fs/promises';
import { resolve, join, sep } from 'node:path';
import { createHash } from 'node:crypto';
import { chromium, type Page } from 'playwright';
import { families, variants, documentFor } from '../tests/final-holdout/families.ts';
import { capturePair } from '../capture/run.ts';
import { writeTensors } from '../capture/tensors.ts';
import { readPng, atomicWrite } from '../capture/png.ts';
import { analyzePair, intersection, LABELS } from '../core/index.ts';
const fixtures = resolve('tests/final-holdout'), output = resolve(process.argv[2] ?? 'artifacts/final-holdout');
const sha = (bytes: Uint8Array | string) => createHash('sha256').update(bytes).digest('hex');
try { await readFile(join(fixtures, 'freeze.json')); throw new Error('Holdout already frozen. Existing fixtures and labels must not be overwritten.'); } catch (error: any) { if (error.code !== 'ENOENT') throw error; }
await mkdir(output, { recursive: true });
for (const family of families) for (const variant of variants) for (const side of ['before', 'after']) await atomicWrite(join(fixtures, family, variant.id, `${side}.html`), documentFor(family, variant, side === 'after'));
const server = createServer(async (request, response) => {
  const path = resolve(fixtures, `.${new URL(request.url ?? '/', 'http://localhost').pathname}`);
  if (!path.startsWith(fixtures + sep)) { response.writeHead(403).end(); return; }
  try { response.setHeader('Content-Type', 'text/html; charset=utf-8'); response.end(await readFile(path)); } catch { response.writeHead(404).end(); }
});
await new Promise<void>(done => server.listen(0, '127.0.0.1', done)); const address = server.address(); if (!address || typeof address === 'string') throw new Error('Fixture server failed.'); const origin = `http://127.0.0.1:${address.port}`;
const browser = await chromium.launch({ headless: true });
async function measure(page: Page, url: string) {
  await page.goto(url); await page.evaluate(async () => { await document.fonts.ready; document.querySelector('#target')!.scrollIntoView({ block: 'center' }); });
  return page.evaluate(() => {
    const target = document.querySelector('#target') as HTMLElement, label = document.querySelector('#target-label') as HTMLElement, container = document.querySelector('#container') as HTMLElement;
    const measured = []; for (const element of [target, label, container]) { const r = element.getBoundingClientRect(); measured.push({ x: r.x + window.scrollX, y: r.y + window.scrollY, width: r.width, height: r.height }); }
    const [t, l, c] = measured; const style = getComputedStyle(target), visible = style.visibility !== 'hidden' && style.display !== 'none' && Number(style.opacity) > 0;
    const lr = label.getBoundingClientRect(); let covered = 0, samples = 0;
    if (visible) for (let y = 0; y < 3; y++) for (let x = 0; x < 12; x++) { const px = lr.x + (x + .5) * lr.width / 12, py = lr.y + (y + .5) * lr.height / 3; if (px < 0 || py < 0 || px >= innerWidth || py >= innerHeight) continue; const hit = document.elementFromPoint(px, py); if (hit && !target.contains(hit)) covered++; samples++; }
    const inside = Math.max(0, Math.min(t.x + t.width, c.x + c.width) - Math.max(t.x, c.x)) * Math.max(0, Math.min(t.y + t.height, c.y + c.height) - Math.max(t.y, c.y));
    return { target: t, label: l, container: c, visible, labelVisibleRatio: Math.min(1, label.clientWidth / label.scrollWidth) * Math.min(1, label.clientHeight / label.scrollHeight), targetOutsideFraction: 1 - inside / (t.width * t.height), coveredFraction: samples ? covered / samples : null, coverageSamples: samples };
  });
}
const cases: any[] = [];
try {
  const page = await browser.newPage({ viewport: { width: 1360, height: 760 } });
  for (const family of families) for (const variant of variants) {
    const id = `${family}/${variant.id}`, beforeUrl = `${origin}/${id}/before.html`, afterUrl = `${origin}/${id}/after.html`, directory = join(output, id);
    const captured = await capturePair({ beforeUrl, afterUrl, outputDir: directory, viewport: { width: 1360, height: 760 }, deviceScaleFactor: 1, readySelector: '[data-ready]', state: { fixedTime: 1700000000000, randomSeed: 307 } }) as any;
    if (captured.execution !== 'complete') throw new Error(`${id}: capture is ${captured.execution}.`);
    const before = await measure(page, beforeUrl), after = await measure(page, afterUrl);
    await writeTensors({ before: join(directory, 'before.png'), after: join(directory, 'after.png'), output: join(directory, 'tensors') });
    const analysis = analyzePair(await readPng(join(directory, 'before.png')), await readPng(join(directory, 'after.png')));
    const moved = Math.hypot(after.target.x - before.target.x, after.target.y - before.target.y) > 2;

    const observations = after.visible ? [Number(after.labelVisibleRatio < before.labelVisibleRatio - .08), before.coveredFraction === null || after.coveredFraction === null ? null : Number(after.coveredFraction > before.coveredFraction + .15), Number(after.targetOutsideFraction > before.targetOutsideFraction + .02), 0, Number(moved)] : [null, null, null, Number(before.visible), 0];
    if (observations.some(v => v === 1) && !analysis.changedPixels) throw new Error(`${id}: proposed positive lacks pixel evidence.`);
    const boxes = [before.target, after.target];
    const fixtureHashes = { before: sha(await readFile(join(fixtures, id, 'before.html'))), after: sha(await readFile(join(fixtures, id, 'after.html'))) };
    const item = { id, family, before: `${id}/before.html`, after: `${id}/after.html`, fixtureHashes, screenshotHashes: { before: captured.before.sha256, after: captured.after.sha256 }, imageSizes: { before: captured.before.imageSize, after: captured.after.imageSize }, observations, expectedRegions: boxes, changedPixels: analysis.changedPixels, candidateCount: analysis.candidates.length, measurementEvidence: { before, after }, intentional: 'intentional' in variant ? variant.intentional : false, provenance: { authoredVariant: variant.id, operation: variant.edit, severity: variant.amount }, annotationMethod: 'Rendered geometry, clipping extent, sampled hit-testing and actual pixel difference; operation provenance does not assign labels.' };
    cases.push(item); process.stdout.write(`${JSON.stringify({ stage: 'holdout_render_verify', completed: cases.length, total: families.length * variants.length, id, observations })}\n`);
  }
  const manifest = { schemaVersion: '1.0', labels: LABELS, families, cases, inferenceExecuted: false, inspectionStatus: 'Rendered measurements verified; visual contact-sheet confirmation required before freeze.', scope: 'Three original structures entirely withheld from training, calibration and selection. This is an internal final check, not external acceptance.' };
  await atomicWrite(join(fixtures, 'manifest.json'), JSON.stringify(manifest, null, 2));
  for (const family of families) {
    const cards = await Promise.all(cases.filter(c => c.family === family).map(async item => {
      const imgs = await Promise.all(['before', 'after'].map(async side => `<div><span>${side}</span><img src="data:image/png;base64,${(await readFile(join(output, item.id, `${side}.png`))).toString('base64')}"></div>`));
      return `<section><h2>${item.provenance.authoredVariant} · ${item.observations.map((x: number | null) => x ?? '?').join(',')}</h2><article>${imgs.join('')}</article></section>`;
    }));
    const sheet = await browser.newPage({ viewport: { width: 1800, height: 1000 } });
    await sheet.setContent(`<html><style>body{margin:0;padding:20px;background:#e9edf3;font:16px Arial}main{display:grid;grid-template-columns:1fr 1fr;gap:20px}section{background:white;padding:12px;height:500px}h2{font-size:18px}article{display:flex;gap:8px}article div{width:49%}img{width:100%;max-height:430px;object-fit:contain;object-position:top}span{display:block}</style><main>${cards.join('')}</main></html>`);
    await sheet.screenshot({ path: join(output, `${family}-contact-sheet.png`), fullPage: true }); await sheet.close();
  }
} finally { await browser.close(); await new Promise<void>((done, reject) => server.close(error => error ? reject(error) : done())); }
