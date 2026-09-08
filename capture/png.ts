import { readFile, writeFile, rename, mkdir } from 'node:fs/promises';
import { dirname } from 'node:path';
import { PNG } from 'pngjs';
import { validateRaster, type Raster, type Mask } from '../core/index.ts';
export { decodePNG as decodePng } from '../core/png.ts';
import { decodePNG as decodePng } from '../core/png.ts';
export async function readPng(path: string): Promise<Raster> { return decodePng(await readFile(path)); }
export async function atomicWrite(path: string, data: string | Uint8Array): Promise<void> { await mkdir(dirname(path), { recursive: true }); const temporary = `${path}.${process.pid}.${Math.random().toString(16).slice(2)}.tmp`; await writeFile(temporary, data); await rename(temporary, path); }
export async function writePng(path: string, raster: Raster): Promise<void> { validateRaster(raster); const png = new PNG({ width: raster.width, height: raster.height }); png.data = Buffer.from(raster.data); await atomicWrite(path, PNG.sync.write(png)); }

export function maskedRaster(raster: Raster, masks: Mask[]): Raster {
  const data = new Uint8Array(raster.data);
  for (const mask of masks) for (let y = Math.max(0, Math.floor(mask.y)); y < Math.min(raster.height, Math.ceil(mask.y + mask.height)); y++) for (let x = Math.max(0, Math.floor(mask.x)); x < Math.min(raster.width, Math.ceil(mask.x + mask.width)); x++) data.fill(255, (y * raster.width + x) * 4, (y * raster.width + x) * 4 + 4);
  return { width: raster.width, height: raster.height, data };
}
