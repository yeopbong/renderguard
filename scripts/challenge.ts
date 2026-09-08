/** Capture the frozen handwritten challenge without importing training generators. */
import { createServer } from 'node:http';
import { readFile, mkdir } from 'node:fs/promises';
import { resolve, join, sep } from 'node:path';
import { createHash } from 'node:crypto';
import { chromium } from 'playwright';
import { capturePair } from '../capture/run.ts';
import { writeTensors } from '../capture/tensors.ts';
import { atomicWrite } from '../capture/png.ts';
const fixtures = resolve('tests/challenge'), output = resolve(process.argv[2] ?? 'artifacts/challenge');
const hash = (data: Uint8Array | string) => createHash('sha256').update(data).digest('hex');
const manifestBytes = await readFile(join(fixtures, 'manifest.json')), manifest = JSON.parse(manifestBytes.toString());
for (const item of manifest.cases) for (const side of ['before', 'after']) if (hash(await readFile(join(fixtures, item[side]))) !== item.fixtureHashes[side]) throw new Error(`Frozen fixture hash mismatch: ${item.id}/${side}.`);
await mkdir(output, { recursive: true });
const server = createServer(async (request, response) => {
  const path = resolve(fixtures, `.${new URL(request.url ?? '/', 'http://localhost').pathname}`);
  if (!path.startsWith(fixtures + sep)) { response.writeHead(403).end(); return; }
  try { response.setHeader('Content-Type', 'text/html; charset=utf-8'); response.end(await readFile(path)); } catch { response.writeHead(404).end(); }
});
await new Promise<void>(done => server.listen(0, '127.0.0.1', done)); const address = server.address(); if (!address || typeof address === 'string') throw new Error('Fixture server failed.'); const origin = `http://127.0.0.1:${address.port}`;
const records: Record<string, any>[] = [];
try {
  for (const item of manifest.cases) {
    const outputDir = join(output, item.id);
    const result = await capturePair({ beforeUrl: `${origin}/${item.before}`, afterUrl: `${origin}/${item.after}`, outputDir, viewport: { width: 480, height: 640 }, readySelector: '[data-ready]', state: { fixedTime: 1700000000000, randomSeed: 71 }, masks: item.masks ?? [], contracts: item.contracts });
    if (result.execution === 'complete') await writeTensors({ before: join(outputDir, 'before.png'), after: join(outputDir, 'after.png'), masks: item.masks, output: join(outputDir, 'tensors') });
    records.push({ id: item.id, execution: result.execution, before: (result.before as any).sha256, after: (result.after as any).sha256, expectedExecution: item.expectedExecution, contractStatuses: (result.contracts as any[]).map(c => c.status), expectedContractStatuses: item.expectedContractStatuses });
    process.stdout.write(`${JSON.stringify({ stage: 'challenge_capture', completed: records.length, total: manifest.cases.length, id: item.id, execution: result.execution })}\n`);
  }
  const report = { schemaVersion: '1.0', manifestSha256: hash(manifestBytes), modelEvaluated: false, records };
  await atomicWrite(join(output, 'capture-results.json'), JSON.stringify(report, null, 2));
  const cards = await Promise.all(manifest.cases.map(async (item: any) => {
    const images = await Promise.all(['before', 'after'].map(async side => `<div><span>${side}</span><img src="data:image/png;base64,${(await readFile(join(output, item.id, `${side}.png`))).toString('base64')}"></div>`));
    return `<section><h2>${item.id}</h2><article>${images.join('')}</article></section>`;
  }));
  const browser = await chromium.launch({ headless: true });
  try { const page = await browser.newPage({ viewport: { width: 1200, height: 800 }, deviceScaleFactor: 1 }); await page.setContent(`<html><style>body{margin:0;padding:20px;font:15px Arial;background:#e9edf3}main{display:grid;grid-template-columns:1fr 1fr;gap:20px}section{background:white;padding:12px;height:400px;overflow:hidden}h2{font-size:18px}article{display:flex;gap:10px}article div{width:49%}span{display:block;margin-bottom:4px;color:#536}img{width:100%;max-height:340px;object-fit:contain;object-position:top}</style><main>${cards.join('')}</main></html>`); await page.screenshot({ path: join(output, 'contact-sheet.png'), fullPage: true }); } finally { await browser.close(); }
} finally { await new Promise<void>((done, reject) => server.close(error => error ? reject(error) : done())); }
