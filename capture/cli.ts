import { readFile } from 'node:fs/promises';
import { capturePair, type CaptureConfig } from './run.ts';
async function main(): Promise<void> {
  const raw = process.argv[2] ? await readFile(process.argv[2], 'utf8') : await new Promise<string>((resolve, reject) => { let text = ''; process.stdin.setEncoding('utf8'); process.stdin.on('data', chunk => { text += chunk; }); process.stdin.on('end', () => resolve(text)); process.stdin.on('error', reject); });
  const result = await capturePair(JSON.parse(raw) as CaptureConfig, progress => process.stderr.write(`${JSON.stringify(progress)}\n`));
  process.stdout.write(`${JSON.stringify(result)}\n`);
}
main().catch(error => { process.stderr.write(`${JSON.stringify({ stage: 'failed', error: error instanceof Error ? error.message : String(error) })}\n`); process.exitCode = 1; });
