
import { createServer } from 'node:http';
import { readFile, mkdir } from 'node:fs/promises';
import { resolve, join, sep } from 'node:path';
import { createHash } from 'node:crypto';
import { capturePair } from '../capture/run.ts';
import { writeTensors } from '../capture/tensors.ts';
import { atomicWrite } from '../capture/png.ts';
if (!process.argv[2]) throw new Error('Supply a new output directory; the frozen original captures are never overwritten.');
const root = resolve('tests/final-holdout'), output = resolve(process.argv[2]), original = resolve('artifacts/final-holdout');
if (output === original || output.startsWith(root + sep) || output === root) throw new Error('Choose a separate output directory outside the frozen fixtures and original captures.');
const sha = (data: Uint8Array) => createHash('sha256').update(data).digest('hex');
const bytes = await readFile(join(root, 'manifest.json')), manifest = JSON.parse(bytes.toString()), freeze = JSON.parse(await readFile(join(root, 'freeze.json'), 'utf8'));
if (sha(bytes) !== freeze.manifestSha256) throw new Error('Frozen manifest checksum mismatch.');
for (const item of manifest.cases) for (const side of ['before', 'after']) if (sha(await readFile(join(root, item[side]))) !== item.fixtureHashes[side]) throw new Error(`Frozen HTML mismatch: ${item.id}/${side}`);
await mkdir(output, { recursive: true });
const server = createServer(async (request, response) => {
  const path = resolve(root, `.${new URL(request.url ?? '/', 'http://localhost').pathname}`);
  if (!path.startsWith(root + sep)) { response.writeHead(403).end(); return; }
  try { response.setHeader('Content-Type', 'text/html; charset=utf-8'); response.end(await readFile(path)); } catch { response.writeHead(404).end(); }
});
await new Promise<void>(done => server.listen(0, '127.0.0.1', done)); const address = server.address(); if (!address || typeof address === 'string') throw new Error('Fixture server failed.'); const origin = `http://127.0.0.1:${address.port}`;
const results = [];
try {
  for (const item of manifest.cases) {
    const outputDir = join(output, item.id), config = manifest.configuration;
    const result = await capturePair({ beforeUrl: `${origin}/${item.before}`, afterUrl: `${origin}/${item.after}`, outputDir, viewport: config.viewport, deviceScaleFactor: config.deviceScaleFactor, readySelector: config.readySelector, state: { fixedTime: config.fixedTime, randomSeed: config.randomSeed } }) as any;
    if (result.execution === 'complete') await writeTensors({ before: join(outputDir, 'before.png'), after: join(outputDir, 'after.png'), output: join(outputDir, 'tensors') });
    const matchesOriginal = result.before.sha256 === item.screenshotHashes.before && result.after.sha256 === item.screenshotHashes.after;
    results.push({ id: item.id, execution: result.execution, hashes: { before: result.before.sha256, after: result.after.sha256 }, matchesOriginal });
    process.stdout.write(`${JSON.stringify({ stage: 'recapture_frozen_holdout', completed: results.length, total: manifest.cases.length, id: item.id, matchesOriginal })}\n`);
  }
  await atomicWrite(join(output, 'reproduction.json'), JSON.stringify({ schemaVersion: '1.0', manifestSha256: freeze.manifestSha256, modelEvaluated: false, labelsModified: false, results }, null, 2));
} finally { await new Promise<void>((done, reject) => server.close(error => error ? reject(error) : done())); }
