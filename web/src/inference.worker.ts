import * as ort from 'onnxruntime-web/wasm';
import { analyzePair, tensorsForCandidate, VERSION, LABELS } from '../../core/index';
import type { Mask, Raster } from '../../core/index';
import { decodePNG } from '../../core/png';
import type { Calibration } from './types';
let session: ort.InferenceSession | undefined;
let manifest: { version: string; sha256: string; modelSha256?: string; preprocessVersion: string; calibrationSha256: string };
let calibration: Calibration;
const digest = async (bytes: Uint8Array) => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes as Uint8Array<ArrayBuffer>)), b => b.toString(16).padStart(2, '0')).join('');
const send = (message: object) => self.postMessage(message);
async function checkedJSON(url: string) { const r = await fetch(url); if (!r.ok) throw new Error(`Asset request failed (${r.status}): ${url.split('/').at(-1)}`); return r.json(); }
async function model(base: string) {
  if (session) return;
  send({type: 'progress', stage: 'Reading model manifest', completed: 0, total: 0});
  manifest = await checkedJSON(`${base}models/manifest.json`);
  const calibrationResponse = await fetch(`${base}models/calibration.json`);
  if (!calibrationResponse.ok) throw new Error(`Calibration download failed (${calibrationResponse.status}).`);
  const calibrationBytes = new Uint8Array(await calibrationResponse.arrayBuffer());
  if (await digest(calibrationBytes) !== manifest.calibrationSha256) throw new Error('Calibration integrity check failed.');
  calibration = JSON.parse(new TextDecoder().decode(calibrationBytes));
  if (manifest.preprocessVersion !== VERSION) throw new Error('Model preprocessing version does not match this application. Reload the matching release.');
  const expected = manifest.modelSha256 || manifest.sha256;
  if (!/^[a-f0-9]{64}$/.test(expected)) throw new Error('Model manifest has no valid SHA-256.');
  if (calibration.modelSha256 !== expected || calibration.preprocessVersion !== VERSION || !Array.isArray(calibration.classes) || calibration.classes.length !== LABELS.length) throw new Error('Calibration does not match model and preprocessing.');
  if (calibration.classes.some((c,i) => c.label !== LABELS[i] || !['calibrated','uncalibrated'].includes(c.status) || !Number.isFinite(c.temperature) || c.temperature <= 0 || !Number.isFinite(c.bias))) throw new Error('Calibration contains invalid class parameters.');
  send({type: 'progress', stage: 'Downloading visual model', completed: 0, total: 0, unit: 'bytes'});
  const response = await fetch(`${base}models/model.onnx`);
  if (!response.ok || !response.body) throw new Error(`Model download failed (${response.status}).`);
  const encoding = response.headers.get('content-encoding');
  const total = encoding && encoding !== 'identity' ? 0 : Number(response.headers.get('content-length') || 0);
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = []; let completed = 0;
  while (true) { const {done, value} = await reader.read(); if (done) break; chunks.push(value); completed += value.length; if (completed > 80 * 1024 * 1024) throw new Error('Model exceeds the 80 MiB browser limit.'); send({type: 'progress', stage: 'Downloading visual model', completed, total, unit: 'bytes'}); }
  const bytes = new Uint8Array(completed); let offset = 0; for (const c of chunks) {bytes.set(c, offset); offset += c.length;}
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
  if (hash !== expected) throw new Error('Model integrity check failed. Downloaded SHA-256 differs from the release manifest.');
  send({type: 'progress', stage: 'Starting CPU inference runtime', completed: 0, total: 0});
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.proxy = false;
  ort.env.wasm.wasmPaths = `${base}runtime/`;
  session = await ort.InferenceSession.create(bytes, {executionProviders: ['wasm'], graphOptimizationLevel: 'all'});
}
async function raster(blob: Blob): Promise<Raster> {
  if (blob.size > 24 * 1024 * 1024) throw new Error('Each PNG must be at most 24 MiB.');
  const header = new Uint8Array(await blob.slice(0, 24).arrayBuffer());
  if (header.length < 24 || [137,80,78,71,13,10,26,10].some((v,i) => header[i] !== v)) throw new Error('Only valid PNG images are accepted.');
  const view = new DataView(header.buffer);
  const width = view.getUint32(16), height = view.getUint32(20);
  if (width < 1 || height < 1 || width > 4096 || width * height > 24000000) throw new Error('Image limit: width 4,096 px; 24 million pixels per image. Use a smaller region.');
  return decodePNG(new Uint8Array(await blob.arrayBuffer()));
}
self.onmessage = async (event: MessageEvent<{base: string; before: Blob; after: Blob; masks: Mask[]; diagnostics?: boolean}>) => {
  const start = performance.now();
  try {
    send({type: 'progress', stage: 'Decoding PNG images', completed: 0, total: 2});
    const before = await raster(event.data.before); send({type: 'progress', stage: 'Decoding PNG images', completed: 1, total: 2});
    const after = await raster(event.data.after);
    send({type: 'progress', stage: 'Finding pixel changes', completed: 0, total: 0});
    const analysis = analyzePair(before, after, event.data.masks);
    await model(event.data.base);
    const trace = event.data.diagnostics ? {rasterBeforeSHA256: await digest(new Uint8Array(before.data)), rasterAfterSHA256: await digest(new Uint8Array(after.data)), tensorSHA256s: [] as {candidateId: string; sha256: string}[]} : undefined;
    const predictions: {candidateId: string; logits: number[]; scores: number[]}[] = []; const inferenceStart = performance.now();
    const keys = ['localBefore','localAfter','contextBefore','contextAfter','geometry'] as const;
    const names = ['local_before','local_after','context_before','context_after','geometry'];
    for (let index = 0; index < analysis.candidates.length; index += 4) {
      const batch = analysis.candidates.slice(index, index + 4);
      const tensors = batch.map(candidate => tensorsForCandidate(before, after, candidate));
      if (trace) for (let t = 0; t < tensors.length; t++) { const values = keys.map(k => tensors[t][k]); const packed = new Float32Array(values.reduce((n,v) => n+v.length,0)); let cursor=0; for (const value of values) {packed.set(value,cursor);cursor+=value.length;} trace.tensorSHA256s.push({candidateId: batch[t].id, sha256: await digest(new Uint8Array(packed.buffer))}); }
      const feeds: Record<string, ort.Tensor> = {};
      keys.forEach((key, k) => { const stride = key === 'geometry' ? 12 : 3 * 96 * 96; const data = new Float32Array(batch.length * stride); tensors.forEach((t,i) => data.set(t[key],i * stride)); feeds[names[k]] = new ort.Tensor('float32',data,key === 'geometry' ? [batch.length,12] : [batch.length,3,96,96]); });
      const result = await session!.run(feeds);
      const output = result.logits || Object.values(result)[0];
      if (output.data.length !== batch.length * LABELS.length) throw new Error('Unexpected model output shape.');
      batch.forEach((candidate, i) => { const logits = Array.from(output.data as Float32Array).slice(i*5,i*5+5); const scores = logits.map((v,k) => {const c = calibration.classes[k]; return 1 / (1 + Math.exp(-(c.status === 'calibrated' ? v / c.temperature + c.bias : v)));}); predictions.push({candidateId: candidate.id, logits, scores}); });
      Object.values(feeds).forEach(t => t.dispose()); Object.values(result).forEach(t => t.dispose());
      send({type: 'progress', stage: 'Examining visual regions', completed: Math.min(index+4,analysis.candidates.length), total: analysis.candidates.length, unit: 'regions'});
    }
    send({type: 'result', analysis, predictions, trace, model: {version: manifest.version, sha256: manifest.modelSha256 || manifest.sha256, preprocessVersion: VERSION}, calibration, timing: {totalMs: performance.now()-start, inferenceMs: performance.now()-inferenceStart}});
  } catch (error) { send({type: 'error', error: error instanceof Error ? error.message : String(error)}); }
};
