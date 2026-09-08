const decisions = ['unreviewed', 'confirm_defect', 'intentional_change', 'uncertain'];
const statuses = ['satisfied', 'violated', 'inconclusive', 'error', 'unchecked'];
const object = (v: unknown): v is Record<string, any> => v !== null && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.trim().length > 0;
const number = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
function sameContract(left: Record<string, any>, right: Record<string, any>): boolean {
  return ['status', 'type', 'selector', 'container', 'other'].every(k => (left[k] ?? null) === (right[k] ?? null));
}
function contractValid(contract: unknown): contract is Record<string, any> {
  if (!object(contract)) return false;
  const items = [contract, ...['before', 'after'].filter(k => k in contract).map(k => contract[k])];
  for (const item of items) {
    if (!object(item) || !statuses.includes(item.status) || !['required-visible', 'inside-container', 'non-overlap'].includes(item.type) ||
        !text(item.selector) || !Array.isArray(item.measurements) || !item.measurements.length) return false;
    if (['satisfied', 'violated'].includes(item.status) && item.measurements.length !== (item.type === 'required-visible' ? 1 : 2)) return false;
    for (const measurement of item.measurements) {
      if (!object(measurement) || !text(measurement.selector) || !number(measurement.matches) || measurement.matches < 0 || measurement.matches % 1) return false;
      if (['satisfied', 'violated'].includes(item.status)) {
        const box = measurement.box;
        if (measurement.matches !== 1 || !object(box) || ['x', 'y', 'width', 'height'].some(k => !number(box[k]))) return false;
      }
    }
  }
  return !('after' in contract) || sameContract(contract, contract.after);
}
function evidenceError(run: unknown): string | undefined {
  if (!object(run)) return 'Report must be a JSON object';
  if (('schemaVersion' in run && run.schemaVersion !== '1.0') ||
      ('reportSchema' in run && run.reportSchema !== 'renderguard-report/1') ||
      !('schemaVersion' in run || 'reportSchema' in run || run.source === 'browser PNG import')) return 'Unsupported report format';
  if (run.execution !== 'complete') return 'Execution or comparison evidence is incomplete';
  if (!text(run.id)) return 'Report identity is missing';
  const analysis = run.analysis;
  if (!object(analysis) || !Array.isArray(analysis.candidates)) return 'Analysis evidence is incomplete';
  if (['width', 'height'].some(k => !number(analysis[k]) || analysis[k] <= 0) ||
      !number(analysis.heightDelta) || !number(analysis.changedPixels) || analysis.changedPixels < 0 ||
      !['regions', 'tiles'].includes(analysis.mode) || !text(analysis.version)) return 'Analysis evidence is incomplete';
  const ids = new Set<string>();
  for (const candidate of analysis.candidates) {
    if (!object(candidate) || !text(candidate.id) || ids.has(candidate.id)) return 'Candidate identities are invalid';
    if (!number(candidate.changedPixels) || candidate.changedPixels < 0) return 'Candidate pixel count is invalid';
    const box = candidate.box;
    if (!object(box) || ['x', 'y', 'width', 'height'].some(k => !number(box[k]) || box[k] < (['width', 'height'].includes(k) ? 1 : 0))) return 'Candidate geometry is invalid';
    ids.add(candidate.id);
  }
  if (analysis.changedPixels > 0 && !ids.size) return 'Candidate evidence is incomplete';
  const model = run.model;
  if (!object(model) || !text(model.version) || typeof model.sha256 !== 'string' || !/^[a-fA-F0-9]{64}$/.test(model.sha256) || model.preprocessVersion !== analysis.version) return 'Model evidence is incomplete';
  if (!Array.isArray(run.predictions)) return 'Model results are incomplete';
  const predicted = new Set<string>();
  for (const prediction of run.predictions) {
    if (!object(prediction) || !text(prediction.candidateId) || !ids.has(prediction.candidateId) || predicted.has(prediction.candidateId)) return 'Prediction associations are invalid';
    for (const key of ['logits', 'scores']) {
      const values = prediction[key];
      if (!Array.isArray(values) || values.length !== 5 || values.some(v => !number(v) || (key === 'scores' && (v < 0 || v > 1)))) return 'Model results are invalid';
    }
    predicted.add(prediction.candidateId);
  }
  if (predicted.size !== ids.size) return 'Model results are incomplete';
  const contracts = 'contracts' in run ? run.contracts : [];
  if (!Array.isArray(contracts)) return 'Contract evidence is invalid';
  const targets = new Set(ids);
  for (const contract of contracts) {
    if (!contractValid(contract) || !text(contract.id) || targets.has(contract.id)) return 'Contract evidence is invalid';
    targets.add(contract.id);
  }
  if ('capture' in run) {
    const capture = run.capture;
    if (!object(capture) || capture.execution !== 'complete' || !Array.isArray(capture.contracts)) return 'Capture evidence is incomplete';
    if (capture.contracts.length !== contracts.length || capture.contracts.some((c, i) => !contractValid(c) || c.id !== contracts[i].id || !sameContract(c, contracts[i]))) return 'Declared contract results are incomplete';
    for (const side of ['before', 'after']) {
      const captured = capture[side];
      if (!object(captured) || !Array.isArray(captured.contracts) || captured.contracts.length !== contracts.length) return 'Declared contract results are incomplete';
      for (let i = 0; i < captured.contracts.length; i++) {
        const contract = captured.contracts[i], expected = contracts[i][side];
        if (!contractValid(contract) || !object(expected) || !sameContract(contract, expected)) return 'Declared contract results are incomplete';
      }
    }
  }
  if (!object(run.decisions)) return 'Review evidence is incomplete';
  for (const [id, review] of Object.entries(run.decisions)) {
    if (!targets.has(id) || !object(review) || !decisions.includes(review.decision)) return 'Review associations or decisions are invalid';
  }
  if ('events' in run) {
    if (!Array.isArray(run.events)) return 'Review history is invalid';
    for (const event of run.events) {
      if (!object(event)) return 'Review history is invalid';
      if (['review', 'undo'].includes(event.kind) && (!text(event.candidateId) || !targets.has(event.candidateId) || event.runId !== run.id)) return 'Review history associations are invalid';
    }
  }
}
export function gateFor(value: unknown): {code: number; reason: string} {
  const error = evidenceError(value);
  if (error) return {code: 3, reason: error};
  const run = value as Record<string, any>;
  const contracts: Record<string, any>[] = run.contracts || [];
  if (contracts.some(c => ['inconclusive', 'error', 'unchecked'].includes(c.status))) return {code: 3, reason: 'A declared requirement could not be checked'};
  if (contracts.some(c => c.status === 'violated') || Object.values(run.decisions).some(d => (d as {decision: string}).decision === 'confirm_defect')) return {code: 2, reason: 'Confirmed defect or declared contract violation'};
  if (run.analysis.candidates.some((c: {id: string}) => run.decisions[c.id]?.decision !== 'intentional_change')) return {code: 1, reason: 'Visual changes remain unreviewed or uncertain'};
  return {code: 0, reason: 'No blocking items under the declared review policy'};
}
