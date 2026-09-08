
import { decode, convertIndexedToRgb } from 'fast-png';
import { InputError, LIMITS, validateRaster, type Raster } from './index.ts';
export function decodePNG(bytes: Uint8Array): Raster {
  if (bytes.byteLength > LIMITS.maxPngBytes) throw new InputError('PNG exceeds the 40 MiB input limit.');
  if (bytes.length < 33 || [137, 80, 78, 71, 13, 10, 26, 10].some((value, i) => bytes[i] !== value)) throw new InputError('Input must be a PNG image.');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength), width = view.getUint32(16), height = view.getUint32(20);
  if (!width || !height || width > LIMITS.maxWidth || height > LIMITS.maxHeight || width * height > LIMITS.maxPixels) throw new InputError('PNG dimensions exceed resource limits.');
  for (let offset = 8; offset + 12 <= bytes.length;) {
    const length = view.getUint32(offset);
    if (length > bytes.length - offset - 12) throw new InputError('Malformed PNG chunk length.');
    const kind = String.fromCharCode(...bytes.subarray(offset + 4, offset + 8));
    if (kind === 'acTL') throw new InputError('Animated PNG is not supported. Import a single-frame PNG.');
    offset += length + 12;
  }
  const decoded = decode(bytes, { checkCrc: true });
  let pixels = decoded.data, channels = decoded.channels;
  if (decoded.palette) { pixels = convertIndexedToRgb(decoded); channels = decoded.palette[0].length; }
  const data = new Uint8Array(width * height * 4), indexed = Boolean(decoded.palette), maximum = (1 << decoded.depth) - 1;
  const unpacked = (p: number, c: number): number => {
    if (indexed || decoded.depth >= 8) return pixels[p * channels + c];
    const y = Math.floor(p / width), x = p % width, rowBytes = Math.ceil(width * channels * decoded.depth / 8), bit = (x * channels + c) * decoded.depth;
    return (pixels[y * rowBytes + Math.floor(bit / 8)] >> (8 - decoded.depth - bit % 8)) & maximum;
  };
  const normalized = (value: number) => indexed || decoded.depth === 8 ? value : Math.round(value * 255 / maximum);
  for (let p = 0; p < width * height; p++) {
    const i = p * 4, gray = !indexed && channels <= 2;
    const rawR = unpacked(p, 0), rawG = gray ? rawR : unpacked(p, 1), rawB = gray ? rawR : unpacked(p, 2);
    data[i] = normalized(rawR); data[i + 1] = normalized(rawG); data[i + 2] = normalized(rawB);
    let alpha = channels === 4 ? normalized(unpacked(p, 3)) : gray && channels === 2 ? normalized(unpacked(p, 1)) : 255;
    const transparency = decoded.transparency;
    if (!indexed && transparency?.length && (gray ? rawR === transparency[0] : rawR === transparency[0] && rawG === transparency[1] && rawB === transparency[2])) alpha = 0;
    data[i + 3] = alpha;
  }
  const raster = { width, height, data }; validateRaster(raster); return raster;
}
