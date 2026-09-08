import { readFile } from 'node:fs/promises';
import { resolve, basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import { analyzePair, differenceRaster, tensorsForCandidate, VERSION, IMAGE_SIZE, GEOMETRY_SIZE, type Mask } from '../core/index.ts';
import { readPng, atomicWrite, writePng, maskedRaster } from './png.ts';
export type TensorRequest = { before: string; after: string; masks?: Mask[]; output: string; saveImages?: boolean };
export async function writeTensors(request: TensorRequest): Promise<Record<string, unknown>> {
  const [before, after] = await Promise.all([readPng(request.before), readPng(request.after)]), analysis = analyzePair(before, after, request.masks);
  const stride = 4 * 3 * IMAGE_SIZE * IMAGE_SIZE + GEOMETRY_SIZE, all = new Float32Array(analysis.candidates.length * stride);
  for (let n = 0; n < analysis.candidates.length; n++) {
    const t = tensorsForCandidate(before, after, analysis.candidates[n]); let offset = n * stride;
    for (const tensor of [t.localBefore, t.localAfter, t.contextBefore, t.contextAfter, t.geometry]) { all.set(tensor, offset); offset += tensor.length; }
  }
  const prefix = request.output.endsWith('.json') ? request.output.slice(0, -5) : request.output;
  await atomicWrite(`${prefix}.f32`, new Uint8Array(all.buffer));
  if (request.saveImages) {
    await writePng(`${prefix}-analysis-before.png`, maskedRaster(before, analysis.masks));
    await writePng(`${prefix}-analysis-after.png`, maskedRaster(after, analysis.masks));
    await writePng(`${prefix}-diff.png`, differenceRaster(before, after, analysis.masks));
  }
  const metadata = { ...analysis, tensor: { path: basename(`${prefix}.f32`), dtype: 'float32', endian: 'little', shape: [analysis.candidates.length, stride], imageShape: [3, IMAGE_SIZE, IMAGE_SIZE], order: ['local_before', 'local_after', 'context_before', 'context_after', 'geometry'], preprocessVersion: VERSION } };
  await atomicWrite(`${prefix}.json`, JSON.stringify(metadata));
  return { output: `${prefix}.json`, candidates: analysis.candidates.length, changedPixels: analysis.changedPixels };
}
async function main(): Promise<void> {
  const raw = process.argv[2] ? await readFile(process.argv[2], 'utf8') : await new Promise<string>((resolveInput, reject) => { let text = ''; process.stdin.setEncoding('utf8'); process.stdin.on('data', chunk => { text += chunk; }); process.stdin.on('end', () => resolveInput(text)); process.stdin.on('error', reject); });
  const input = JSON.parse(raw) as TensorRequest | TensorRequest[] | { pairs: TensorRequest[] };
  const requests: TensorRequest[] = Array.isArray(input) ? input : 'pairs' in input ? input.pairs : [input];
  const results = [];
  for (const request of requests) { results.push(await writeTensors(request)); if (requests.length > 1) process.stderr.write(`${JSON.stringify({ stage: 'tensors', completed: results.length, total: requests.length })}\n`); }
  process.stdout.write(`${JSON.stringify(Array.isArray(input) || 'pairs' in input ? { results } : results[0])}\n`);
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(error => { process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`); process.exitCode = 1; });
