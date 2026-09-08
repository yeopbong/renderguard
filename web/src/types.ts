import type { Candidate, Mask } from '../../core/index';
export const LABEL_NAMES: Record<string, string> = { clipping: 'Clipping', overlap_or_occlusion: 'Overlap / occlusion', out_of_container: 'Outside container', element_disappearance: 'Element disappearance', layout_displacement: 'Layout displacement' };
export type Decision = 'unreviewed' | 'confirm_defect' | 'intentional_change' | 'uncertain';
export type Review = { decision: Decision; observation?: Record<string, boolean | null> };
export type ReviewEvent = { id: string; time: string; candidateId: string; oldValue: Review; newValue: Review; modelVersion: string; runId: string; kind: 'review' | 'undo'; undoes?: string };
export type Calibration = { modelSha256: string; preprocessVersion: string; classes: { label: string; status: 'calibrated' | 'uncalibrated'; temperature: number; bias: number; n: number; positive: number; negative: number }[] };
export type Run = { id: string; projectId: string; name?: string; createdAt: string; execution: 'complete' | 'error' | 'cancelled' | 'incomparable'; environment: 'verified' | 'unverified'; model: { version: string; sha256: string; preprocessVersion?: string }; analysis: { candidates: Candidate[]; width: number; height: number; heightDelta: number; changedPixels: number; mode: 'regions' | 'tiles'; version: string; associations?: {kind:string;fromCandidateId:string;toCandidateId:string;meanColorError:number;scope:string}[] }; predictions: {candidateId: string; logits: number[]; scores: number[]}[]; calibration?: Calibration; contracts: {type: string; status: string; selector?: string; reason?: string; [k: string]: unknown}[]; decisions: Record<string, Review>; gate: {code: number; reason: string}; beforeUrl: string; afterUrl: string; masks: Mask[]; events: ReviewEvent[]; images?: { before: string; after: string }; timing?: { totalMs: number; inferenceMs: number }; source?: string; error?: {stage:string;message:string}; reviewPriority?: {weights: Record<string,number>; rule:string} };
export type Baseline = {runId?: string; imageId?: string; imageUrl?: string; sha256?: string; side: 'before'|'after'; environment?: string};
export type BaselineEvent = {id: string; runId?: string; side?: 'before'|'after'; time?: string; createdAt?: string; reverted?: boolean; baseline?: Baseline; new?: Baseline | null; old?: Baseline | null; undoOf?: string};
export type Project = { id: string; name: string; createdAt: string; baselineHistory: BaselineEvent[]; baseline?: Baseline };
export function gateFor(run: Run): {code: number; reason: string} {
  if (run.execution !== 'complete') return {code: 3, reason: `Analysis ${run.execution}`};
  if (run.contracts.some(c => c.status === 'inconclusive' || c.status === 'error')) return {code: 3, reason: 'Required contract evidence is incomplete'};
  if (run.contracts.some(c => c.status === 'violated') || Object.values(run.decisions).some(d => d.decision === 'confirm_defect')) return {code: 2, reason: 'Confirmed defect or contract violation'};
  if (run.analysis.candidates.some(c => !run.decisions[c.id] || !['intentional_change'].includes(run.decisions[c.id].decision))) return {code: 1, reason: 'Changes need a human decision'};
  return {code: 0, reason: run.analysis.candidates.length ? 'All visual changes reviewed as intentional' : 'No unmasked pixel changes detected'};
}
