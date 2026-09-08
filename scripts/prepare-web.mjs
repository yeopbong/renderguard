import { copyFile, mkdir, readdir } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const source = resolve(root, 'node_modules/onnxruntime-web/dist');
const target = resolve(root, 'web/public/runtime');
await mkdir(target, { recursive: true });
// Runtime and binary are copied from the same pinned package.
for (const name of await readdir(source)) {
  if (/^ort-wasm-simd-threaded\.(wasm|mjs)$/.test(name)) await copyFile(resolve(source, name), resolve(target, name));
}
console.log('Browser CPU runtime prepared.');
