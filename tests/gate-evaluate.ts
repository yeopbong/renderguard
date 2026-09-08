import { readFileSync } from 'node:fs';
import { gateFor, type Run } from '../web/src/types';
import { makeJSONReport, makeReport } from '../web/src/report';
const reports: Run[] = JSON.parse(readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(process.argv.includes('--exports')
  ? reports.map(run => ({json: JSON.parse(makeJSONReport(run)).gate, html: makeReport(run)}))
  : reports.map(gateFor)));
