import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  base: process.env.RENDERGUARD_BASE || '/renderguard/',
  plugins: [react()],
  build: { outDir: '../dist', emptyOutDir: true, sourcemap: false, target: 'es2022' },
  worker: { format: 'es' },
  server: { host: '127.0.0.1', port: 5173, proxy: { '/api': 'http://127.0.0.1:8765' } },
});
