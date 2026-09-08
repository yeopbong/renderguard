import test from 'node:test';
import assert from 'node:assert/strict';
import { analyzePair, associateCandidates, tensorsForCandidate, tensorForCrop, differenceRaster, LIMITS, VERSION, type Raster, type Mask } from '../core/index.ts';
import { decodePng, writePng, readPng } from '../capture/png.ts';
import { evaluateGeometry, type Measurement } from '../capture/contracts.ts';
import { assertAllowedTarget, normalizedOrigin } from '../capture/security.ts';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const raster = (width: number, height: number, value = 255): Raster => { const data = new Uint8Array(width * height * 4); for (let i = 0; i < data.length; i += 4) { data[i] = data[i + 1] = data[i + 2] = value; data[i + 3] = 255; } return { width, height, data }; };
const paint = (image: Raster, x: number, y: number, w: number, h: number, value: number) => { for (let j = y; j < y + h; j++) for (let k = x; k < x + w; k++) for (let c = 0; c < 3; c++) image.data[(j * image.width + k) * 4 + c] = value; };
test('identical images have no candidates and one-level one-pixel changes remain reviewable', () => {
  const a = raster(128, 96), b = raster(128, 96);
  assert.equal(analyzePair(a, b).changedPixels, 0); paint(b, 37, 21, 1, 1, 254);
  const result = analyzePair(a, b); assert.equal(result.changedPixels, 1); assert.equal(result.candidates.length, 1); assert.deepEqual(result.candidates[0].box, { x: 37, y: 21, width: 1, height: 1 }); assert.equal(result.rawDifference.threshold, 0);
});
test('eight-connected components and multiscale merging preserve all changed pixels', () => {
  const a = raster(300, 180), b = raster(300, 180); paint(b, 10, 10, 5, 5, 0); paint(b, 15, 15, 5, 5, 0); paint(b, 31, 14, 8, 8, 0); paint(b, 200, 150, 3, 2, 0);
  const result = analyzePair(a, b); assert.equal(result.changedPixels, 120); assert.equal(result.candidates.reduce((sum, c) => sum + c.changedPixels, 0), 120); assert.equal(result.candidates.length, 2);
});
test('declared masks exclude diff and tensor pixels consistently while preserving inputs', () => {
  const a = raster(128, 96), b = raster(128, 96); paint(b, 10, 10, 6, 6, 0); paint(b, 30, 12, 5, 5, 0);
  const masks: Mask[] = [{ x: 10, y: 10, width: 6, height: 6, source: 'User: timestamp' }]; const result = analyzePair(a, b, masks);
  assert.equal(result.changedPixels, 25); assert.equal(result.excludedPixels, 36); assert.equal(b.data[(10 * 128 + 10) * 4], 0);
  const sanitized = raster(128, 96); paint(sanitized, 30, 12, 5, 5, 0);
  const originalTensor = tensorsForCandidate(a, b, result.candidates[0]); const sanitizedTensor = tensorsForCandidate(a, sanitized, result.candidates[0]);
  assert.deepEqual(originalTensor.localAfter, sanitizedTensor.localAfter); assert.deepEqual(originalTensor.contextAfter, sanitizedTensor.contextAfter);
  assert.throws(() => analyzePair(a, b, [{ ...masks[0], source: '' }]), /source/);
});
test('height changes preserve origin and validity including a blank new page tail', () => {
  const a = raster(100, 100), b = raster(100, 150); const result = analyzePair(a, b);
  assert.equal(result.heightDelta, 50); assert.equal(result.changedPixels, 5000); assert.equal(result.validRegions.before.height, 100); assert.equal(result.validRegions.after.height, 150);
  assert.deepEqual(result.candidates[0].box, { x: 0, y: 100, width: 100, height: 50 }); assert.equal(result.candidates[0].stats[3], 0); assert.equal(result.candidates[0].stats[4], 1);
  const diff = differenceRaster(a, b); assert.equal(diff.height, 150); assert.equal(diff.data[(100 * 100) * 4 + 2], 220);
  assert.throws(() => analyzePair(a, raster(99, 100)), /widths differ/);
});
test('large full-page changes use tiles with no lost tail or seam pixels', () => {
  const a = raster(120, 2400), b = raster(120, 2400, 0); const result = analyzePair(a, b);
  assert.equal(result.mode, 'tiles'); assert.equal(result.changedPixels, 288000); assert.equal(result.candidates.reduce((sum, c) => sum + c.changedPixels, 0), 288000);
  assert.equal(Math.max(...result.candidates.map(c => c.box.y + c.box.height)), 2400);
  const ids = result.candidates.map(c => c.id); assert.equal(new Set(ids).size, ids.length);
});
test('resource bounds reject dimensions before buffer handling', () => {
  assert.throws(() => analyzePair({ width: LIMITS.maxWidth + 1, height: 1, data: new Uint8Array() }, raster(1, 1)), /resource limits/);
  assert.throws(() => analyzePair({ width: 10, height: 10, data: new Uint8Array(3) }, raster(10, 10)), /RGBA/);
});
test('transparent pixels composite white and half-pixel bilinear letterbox is deterministic', () => {
  const a = raster(2, 1, 0); a.data[3] = 0; a.data[7] = 128;
  const b = raster(2, 1, 255); paint(b, 1, 0, 1, 1, 127);
  assert.equal(analyzePair(a, b).changedPixels, 0);
  const crop = { x: 0, y: 0, width: 2, height: 1 }, t = tensorForCrop(a, crop); assert.deepEqual(t, tensorForCrop(a, crop));
  assert.ok(Math.abs(t[0] - (1 - 0.485) / 0.229) < 1e-6);
  const center = t[48 * 96 + 48]; assert.ok(center > -0.1 && center < 2.3);
  const result = analyzePair(raster(96, 96), raster(96, 96, 0)); const tensors = tensorsForCandidate(raster(96, 96), raster(96, 96, 0), result.candidates[0]);
  assert.equal(tensors.geometry.length, 12); assert.equal(tensors.localBefore.length, 3 * 96 * 96); assert.equal(result.version, VERSION); assert.notDeepEqual(tensors.localBefore, tensors.localAfter);
});
test('PNG round-trip matches exact RGBA decode and malformed files fail', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'renderguard-png-'));
  try { const a = raster(32, 24); paint(a, 9, 2, 7, 5, 37); await writePng(join(directory, 'input.png'), a); const b = await readPng(join(directory, 'input.png')); assert.deepEqual(b, a); assert.deepEqual(decodePng(await readFile(join(directory, 'input.png'))), a); assert.throws(() => decodePng(new Uint8Array([1, 2, 3])), /PNG/); } finally { await rm(directory, { recursive: true, force: true }); }
});
const measured = (selector: string, x: number, y: number, width: number, height: number): Measurement => ({ selector, matches: 1, box: { x, y, width, height }, displayed: true, inPage: true });
test('unmeasurable and ambiguous explicit contracts remain inconclusive', () => {
  assert.equal(evaluateGeometry({ type: 'required-visible', selector: '.item' }, [{ selector: '.item', matches: 2 }]).status, 'inconclusive');
  assert.equal(evaluateGeometry({ type: 'inside-container', selector: '.item', container: '.parent' }, [measured('.item', 1, 1, 10, 10), { selector: '.parent', matches: 0 }]).status, 'inconclusive');
  assert.equal(evaluateGeometry({ type: 'required-visible', selector: '.item' }, [{ ...measured('.item', 0, 0, 0, 0), displayed: false }]).status, 'violated');
});
test('constraints use CSS geometry and tolerance without claiming actual occlusion', () => {
  const a = measured('#a', 10, 10, 40, 40), b = measured('#b', 49.5, 0, 50, 100);
  const overlap = evaluateGeometry({ type: 'non-overlap', selector: '#a', other: '#b', tolerance: 1 }, [a, b]); assert.equal(overlap.status, 'satisfied');
  const strict = evaluateGeometry({ type: 'non-overlap', selector: '#a', other: '#b', tolerance: 0 }, [a, b]); assert.equal(strict.status, 'violated'); assert.match(strict.reason, /not proof of occlusion/);
  assert.equal(evaluateGeometry({ type: 'inside-container', selector: '#a', container: '#c' }, [a, measured('#c', 0, 0, 49, 49)]).status, 'satisfied');
});
test('development target policy restricts redirects, credentials, hostnames and workbench access', () => {
  const policy = { allowedTargets: ['http://localhost:4000'], deniedPorts: [8765] };
  assert.equal(assertAllowedTarget('http://localhost:4000/path?a=1', policy).hostname, 'localhost');
  for (const value of ['file:///etc/passwd', 'http://example.com', 'http://127.1:4000', 'http://localhost:5000', 'http://user:secret@localhost:4000']) assert.throws(() => assertAllowedTarget(value, policy));
  assert.throws(() => assertAllowedTarget('http://localhost:8765/api/session', { allowedTargets: ['http://localhost:8765'] }), /workbench/);
  assert.equal(normalizedOrigin('http://[::1]:4000/path'), 'http://[::1]:4000');
});

test('separated translated regions gain heuristic associations without changing tensors or candidates', () => {
  const before = raster(480, 180), after = raster(480, 180); paint(before, 20, 30, 90, 70, 20); paint(after, 310, 30, 90, 70, 20);
  const analysis = analyzePair(before, after), original = JSON.parse(JSON.stringify(analysis.candidates));
  assert.equal(analysis.candidates.length, 2); assert.equal(analysis.associations.length, 1); assert.match(analysis.associations[0].scope, /heuristic/);
  const tensors = analysis.candidates.map(candidate => tensorsForCandidate(before, after, candidate));
  assert.deepEqual(associateCandidates(before, after, analysis.candidates), analysis.associations); assert.deepEqual(analysis.candidates, original);
  assert.deepEqual(analysis.candidates.map(candidate => tensorsForCandidate(before, after, candidate)), tensors);
  const unrelated = raster(480, 180); paint(unrelated, 310, 30, 90, 70, 170); assert.equal(analyzePair(before, unrelated).associations.length, 0);
});
