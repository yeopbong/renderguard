
export const VERSION = 'rgba-diff-rle-letterbox-v1';
export const IMAGE_SIZE = 96;
export const GEOMETRY_SIZE = 12;
export const LABELS = ['clipping', 'overlap_or_occlusion', 'out_of_container', 'element_disappearance', 'layout_displacement'] as const;
export const LIMITS = Object.freeze({ maxWidth: 4096, maxHeight: 32768, maxPixels: 33554432, maxCandidates: 256, maxBatchCandidates: 16, maxMasks: 256, maxPngBytes: 40 * 1024 * 1024 });
export type Rect = { x: number; y: number; width: number; height: number };
export type Raster = { width: number; height: number; data: Uint8Array | Uint8ClampedArray };
export type Mask = Rect & { source: string };
export type Candidate = { id: string; box: Rect; changedPixels: number; stats: number[]; masks?: Mask[] };
export type Analysis = { candidates: Candidate[]; associations: CandidateAssociation[]; width: number; height: number; heightDelta: number; changedPixels: number; mode: 'regions' | 'tiles'; version: string; masks: Mask[]; validRegions: { before: Rect; after: Rect }; excludedPixels: number; rawDifference: { changedPixels: number; maxChannelDifference: number; threshold: number }; limits: typeof LIMITS };
export class InputError extends Error { constructor(message: string) { super(message); this.name = 'InputError'; } }
export function validateRaster(raster: Raster): void {
  const { width, height, data } = raster;
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1) throw new InputError('Image dimensions must be positive integers.');
  if (width > LIMITS.maxWidth || height > LIMITS.maxHeight || width * height > LIMITS.maxPixels) throw new InputError(`Image exceeds resource limits (${LIMITS.maxWidth}px wide, ${LIMITS.maxHeight}px high, ${LIMITS.maxPixels} pixels). Partition the input.`);
  if (data.length !== width * height * 4) throw new InputError('Expected an RGBA image buffer.');
}
export function validateMasks(masks: Mask[]): Mask[] {
  if (masks.length > LIMITS.maxMasks) throw new InputError('Too many masks.');
  return masks.map(mask => {
    if (![mask.x, mask.y, mask.width, mask.height].every(Number.isFinite) || mask.width <= 0 || mask.height <= 0 || typeof mask.source !== 'string' || !mask.source.trim()) throw new InputError('Every mask requires finite geometry, positive dimensions, and a source.');
    return { x: mask.x, y: mask.y, width: mask.width, height: mask.height, source: mask.source.slice(0, 500) };
  });
}
const clip = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));
export function intersection(a: Rect, b: Rect): Rect { const x = Math.max(a.x, b.x), y = Math.max(a.y, b.y); return { x, y, width: Math.max(0, Math.min(a.x + a.width, b.x + b.width) - x), height: Math.max(0, Math.min(a.y + a.height, b.y + b.height) - y) }; }
const area = (rect: Rect) => rect.width * rect.height;
const union = (a: Rect, b: Rect): Rect => ({ x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.max(a.x + a.width, b.x + b.width) - Math.min(a.x, b.x), height: Math.max(a.y + a.height, b.y + b.height) - Math.min(a.y, b.y) });
function maskMap(width: number, height: number, masks: Mask[]): Uint8Array {
  const map = new Uint8Array(width * height);
  for (const m of masks) {
    const x0 = clip(Math.floor(m.x), 0, width), y0 = clip(Math.floor(m.y), 0, height), x1 = clip(Math.ceil(m.x + m.width), 0, width), y1 = clip(Math.ceil(m.y + m.height), 0, height);
    for (let y = y0; y < y1; y++) map.fill(1, y * width + x0, y * width + x1);
  }
  return map;
}

function channel(image: Raster, x: number, y: number, c: number): number {
  if (x < 0 || y < 0 || x >= image.width || y >= image.height) return 255;
  const i = (y * image.width + x) * 4, a = image.data[i + 3];
  return Math.round((image.data[i + c] * a + 255 * (255 - a)) / 255);
}
type Evidence = { changed: Uint8Array; strength: Uint8Array; excluded: Uint8Array; total: number; excludedCount: number; max: number; width: number; height: number };
function evidence(before: Raster, after: Raster, masks: Mask[]): Evidence {
  validateRaster(before); validateRaster(after);
  if (before.width !== after.width) throw new InputError('Image widths differ. Use the same viewport width; image stretching is not supported.');
  const width = before.width, height = Math.max(before.height, after.height);
  const changed = new Uint8Array(width * height), strength = new Uint8Array(width * height), excluded = maskMap(width, height, masks);
  let total = 0, excludedCount = 0, max = 0;
  for (let y = 0, p = 0; y < height; y++) for (let x = 0; x < width; x++, p++) {
    if (excluded[p]) { excludedCount++; continue; }
    const missing = y >= before.height || y >= after.height;
    let diff = missing ? 255 : 0;
    if (!missing) for (let c = 0; c < 3; c++) diff = Math.max(diff, Math.abs(channel(before, x, y, c) - channel(after, x, y, c)));
    strength[p] = diff;
    if (diff > 0) { changed[p] = 1; total++; max = Math.max(max, diff); }
  }
  return { changed, strength, excluded, total, excludedCount, max, width, height };
}

export function differenceRaster(before: Raster, after: Raster, masks: Mask[] = []): Raster {
  const e = evidence(before, after, validateMasks(masks)), data = new Uint8ClampedArray(e.width * e.height * 4);
  for (let p = 0; p < e.changed.length; p++) {
    const i = p * 4, y = Math.floor(p / e.width), missing = y >= before.height || y >= after.height;
    data[i] = e.excluded[p] ? 120 : e.changed[p] ? 235 : 245;
    data[i + 1] = e.excluded[p] ? 120 : e.changed[p] ? (missing ? 40 : 78) : 245;
    data[i + 2] = e.excluded[p] ? 120 : e.changed[p] ? (missing ? 220 : 72) : 245;
    data[i + 3] = 255;
  }
  return { width: e.width, height: e.height, data };
}
type Region = { box: Rect; changedPixels: number };

function components(e: Evidence): Region[] | null {
  type Run = { x0: number; x1: number; id: number };
  const parent: number[] = [], regions: Region[] = [];
  const root = (id: number): number => { let r = id; while (parent[r] !== r) r = parent[r]; while (parent[id] !== id) { const next = parent[id]; parent[id] = r; id = next; } return r; };
  const join = (a: number, b: number) => { a = root(a); b = root(b); if (a !== b) parent[b] = a; };
  let previous: Run[] = [];
  for (let y = 0; y < e.height; y++) {
    const current: Run[] = []; let cursor = 0;
    for (let x = 0; x < e.width;) {
      if (!e.changed[y * e.width + x]) { x++; continue; }
      const x0 = x; while (x < e.width && e.changed[y * e.width + x]) x++;
      const id = regions.length; if (id > 60000) return null;
      parent.push(id); regions.push({ box: { x: x0, y, width: x - x0, height: 1 }, changedPixels: x - x0 });
      while (cursor < previous.length && previous[cursor].x1 < x0 - 1) cursor++;
      for (let k = cursor; k < previous.length && previous[k].x0 <= x; k++) join(id, previous[k].id);
      current.push({ x0, x1: x - 1, id });
    }
    previous = current;
  }
  const merged = new Map<number, Region>();
  for (let id = 0; id < regions.length; id++) { const r = root(id), region = regions[id], old = merged.get(r); if (old) { old.box = union(old.box, region.box); old.changedPixels += region.changedPixels; } else merged.set(r, { box: { ...region.box }, changedPixels: region.changedPixels }); }
  return Array.from(merged.values());
}
function gap(a: Rect, b: Rect): number { return Math.max(Math.max(a.x - b.x - b.width, b.x - a.x - a.width, 0), Math.max(a.y - b.y - b.height, b.y - a.y - a.height, 0)); }
function mergeScales(input: Region[]): Region[] | null {
  if (input.length > 3000) return null;
  let regions = input;
  for (const distance of [3, 12, 28]) {
    const merged: Region[] = [];
    for (const region of regions.sort((a, b) => a.box.y - b.box.y || a.box.x - b.box.x)) {
      let next = { box: { ...region.box }, changedPixels: region.changedPixels };
      for (let k = merged.length - 1; k >= 0; k--) {
        const old = merged[k];
        if (gap(old.box, next.box) <= distance) {
          const combined = union(old.box, next.box);

          if (area(combined) <= (area(old.box) + area(next.box) + 64) * 4 && combined.height <= 1024 && combined.width <= 2048) {
            next = { box: combined, changedPixels: next.changedPixels + old.changedPixels }; merged.splice(k, 1);
          }
        }
      }
      merged.push(next);
    }
    regions = merged;
  }
  return regions;
}

function tileRegions(e: Evidence): Region[] {
  const size = 512, regions: Region[] = [];
  for (let y0 = 0; y0 < e.height; y0 += size) for (let x0 = 0; x0 < e.width; x0 += size) {
    let count = 0, left = e.width, top = e.height, right = -1, bottom = -1;
    for (let y = y0; y < Math.min(y0 + size, e.height); y++) for (let x = x0; x < Math.min(x0 + size, e.width); x++) if (e.changed[y * e.width + x]) { count++; left = Math.min(left, x); right = Math.max(right, x); top = Math.min(top, y); bottom = Math.max(bottom, y); }
    if (count) regions.push({ box: { x: left, y: top, width: right - left + 1, height: bottom - top + 1 }, changedPixels: count });
  }
  if (regions.length > LIMITS.maxCandidates) throw new InputError(`Changes require ${regions.length} review tiles, exceeding ${LIMITS.maxCandidates}. Partition the page; no changes were silently omitted.`);
  return regions;
}
export function analyzePair(before: Raster, after: Raster, suppliedMasks: Mask[] = []): Analysis {
  const masks = validateMasks(suppliedMasks), e = evidence(before, after, masks);
  const connected = components(e), merged = connected && mergeScales(connected);
  const mode = !merged || merged.length > LIMITS.maxCandidates || merged.some(r => r.box.height > 1536 || area(r.box) > 2097152) ? 'tiles' : 'regions';
  const regions = mode === 'tiles' ? tileRegions(e) : merged!;
  const validRegions = { before: { x: 0, y: 0, width: before.width, height: before.height }, after: { x: 0, y: 0, width: after.width, height: after.height } };
  const candidates = regions.sort((a, b) => a.box.y - b.box.y || a.box.x - b.box.x).map((r, index) => {
    let sum = 0, max = 0, excluded = 0;
    for (let y = r.box.y; y < r.box.y + r.box.height; y++) for (let x = r.box.x; x < r.box.x + r.box.width; x++) { const p = y * e.width + x; sum += e.strength[p]; max = Math.max(max, e.strength[p]); excluded += e.excluded[p]; }
    const boxArea = area(r.box);
    return { id: `region-${index + 1}`, ...r, stats: [r.changedPixels / boxArea, sum / boxArea / 255, max / 255, area(intersection(r.box, validRegions.before)) / boxArea, area(intersection(r.box, validRegions.after)) / boxArea, excluded / boxArea], masks };
  });
  return { candidates, associations: associateCandidates(before, after, candidates), width: e.width, height: e.height, heightDelta: after.height - before.height, changedPixels: e.total, mode, version: VERSION, masks, validRegions, excludedPixels: e.excludedCount, rawDifference: { changedPixels: e.total, maxChannelDifference: e.max, threshold: 0 }, limits: LIMITS };
}
function expanded(box: Rect, padding: number): Rect { return { x: Math.floor(box.x - padding), y: Math.floor(box.y - padding), width: Math.ceil(box.width + padding * 2), height: Math.ceil(box.height + padding * 2) }; }
function masked(x: number, y: number, masks: Mask[]): boolean { return masks.some(m => x >= Math.floor(m.x) && x < Math.ceil(m.x + m.width) && y >= Math.floor(m.y) && y < Math.ceil(m.y + m.height)); }

export function tensorForCrop(image: Raster, crop: Rect, masks: Mask[] = []): Float32Array {
  const size = IMAGE_SIZE, means = [0.485, 0.456, 0.406], stds = [0.229, 0.224, 0.225];
  const scale = Math.min(size / crop.width, size / crop.height), targetW = Math.max(1, Math.round(crop.width * scale)), targetH = Math.max(1, Math.round(crop.height * scale));
  const offsetX = Math.floor((size - targetW) / 2), offsetY = Math.floor((size - targetH) / 2), tensor = new Float32Array(3 * size * size);
  const sample = (x: number, y: number, c: number) => masked(x, y, masks) ? 255 : channel(image, x, y, c);
  for (let c = 0; c < 3; c++) for (let oy = 0; oy < size; oy++) for (let ox = 0; ox < size; ox++) {
    let value = 255;
    if (ox >= offsetX && ox < offsetX + targetW && oy >= offsetY && oy < offsetY + targetH) {
      const sx = clip((ox - offsetX + 0.5) * crop.width / targetW - 0.5, 0, crop.width - 1) + crop.x;
      const sy = clip((oy - offsetY + 0.5) * crop.height / targetH - 0.5, 0, crop.height - 1) + crop.y;
      const x0 = Math.floor(sx), y0 = Math.floor(sy), x1 = Math.min(x0 + 1, crop.x + crop.width - 1), y1 = Math.min(y0 + 1, crop.y + crop.height - 1), dx = sx - x0, dy = sy - y0;
      value = sample(x0, y0, c) * (1 - dx) * (1 - dy) + sample(x1, y0, c) * dx * (1 - dy) + sample(x0, y1, c) * (1 - dx) * dy + sample(x1, y1, c) * dx * dy;
    }
    tensor[c * size * size + oy * size + ox] = (value / 255 - means[c]) / stds[c];
  }
  return tensor;
}
export function tensorsForCandidate(before: Raster, after: Raster, candidate: Candidate): { localBefore: Float32Array; localAfter: Float32Array; contextBefore: Float32Array; contextAfter: Float32Array; geometry: Float32Array } {
  const box = candidate.box, height = Math.max(before.height, after.height), width = before.width, largest = Math.max(box.width, box.height);
  const local = expanded(box, Math.max(8, largest * 0.08)), context = expanded(box, Math.max(40, largest * 0.65)), masks = candidate.masks ?? [], stats = candidate.stats;
  const geometry = new Float32Array([box.x / width, box.y / height, box.width / width, box.height / height, stats[0], stats[1], stats[2], stats[3], stats[4], (after.height - before.height) / height, Math.min(8, box.width / box.height) / 8, stats[5]]);
  return { localBefore: tensorForCrop(before, local, masks), localAfter: tensorForCrop(after, local, masks), contextBefore: tensorForCrop(before, context, masks), contextAfter: tensorForCrop(after, context, masks), geometry };
}

export type CandidateAssociation = { kind: 'possible_translation'; fromCandidateId: string; toCandidateId: string; meanColorError: number; scope: string };

export function associateCandidates(before: Raster, after: Raster, candidates: Candidate[]): CandidateAssociation[] {
  const matches: { a: number; b: number; error: number }[] = [], grid = 8;
  const comparison = (first: Raster, a: Rect, second: Raster, b: Rect, masks: Mask[]) => {
    let sum = 0, samples = 0;
    for (let y = 0; y < grid; y++) for (let x = 0; x < grid; x++) {
      const ax = Math.floor(a.x + (x + .5) * a.width / grid), ay = Math.floor(a.y + (y + .5) * a.height / grid), bx = Math.floor(b.x + (x + .5) * b.width / grid), by = Math.floor(b.y + (y + .5) * b.height / grid);
      if (ay >= first.height || by >= second.height || masked(ax, ay, masks) || masked(bx, by, masks)) continue;
      for (let c = 0; c < 3; c++) { sum += Math.abs(channel(first, ax, ay, c) - channel(second, bx, by, c)); samples++; }
    }
    return samples >= grid * grid ? sum / samples / 255 : 1;
  };
  for (let a = 0; a < candidates.length; a++) for (let b = a + 1; b < candidates.length; b++) {
    const first = candidates[a], second = candidates[b], boxA = first.box, boxB = second.box;
    if (area(intersection(boxA, boxB)) > 0 || gap(boxA, boxB) > 640 || Math.min(boxA.width, boxA.height, boxB.width, boxB.height) < 8) continue;
    const widthRatio = boxA.width / boxB.width, heightRatio = boxA.height / boxB.height;
    if (widthRatio < .8 || widthRatio > 1.25 || heightRatio < .8 || heightRatio > 1.25) continue;
    const masks = first.masks ?? [], changeA = comparison(before, boxA, after, boxA, masks), changeB = comparison(before, boxB, after, boxB, masks);
    if (Math.min(changeA, changeB) < .045) continue;
    const error = (comparison(before, boxA, after, boxB, masks) + comparison(before, boxB, after, boxA, masks)) / 2;
    if (error < .055 && error < Math.min(changeA, changeB) * .3) matches.push({ a, b, error });
  }
  const paired = new Set<number>(), result: CandidateAssociation[] = [];
  for (const match of matches.sort((a, b) => a.error - b.error || a.a - b.a || a.b - b.b)) {
    if (paired.has(match.a) || paired.has(match.b)) continue;
    paired.add(match.a); paired.add(match.b);
    result.push({ kind: 'possible_translation', fromCandidateId: candidates[match.a].id, toCandidateId: candidates[match.b].id, meanColorError: match.error, scope: 'Bidirectional image similarity heuristic; neither movement direction nor causal explanation is established.' });
  }
  return result;
}
