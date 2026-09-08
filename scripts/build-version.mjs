import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';

let sourceSha = 'source-archive';
try { sourceSha = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(); } catch {}
const application = JSON.parse(readFileSync('package.json', 'utf8'));
const manifest = JSON.parse(readFileSync('web/public/models/manifest.json', 'utf8'));
writeFileSync('dist/version.json', JSON.stringify({
  schemaVersion: '1.0', sourceSha, version: application.version, modelVersion: manifest.version,
  modelSha256: manifest.sha256, calibrationSha256: manifest.calibrationSha256,
  preprocessingVersion: manifest.preprocessVersion,
}, null, 2) + '\n');
