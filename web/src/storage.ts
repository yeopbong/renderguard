import { gateFor, type Baseline, type Project, type Review, type Run } from './types';
const DB_NAME = 'renderguard-workbench-v1';
let database: Promise<IDBDatabase>;
function db() {
  return database ||= new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => { for (const name of ['projects', 'runs']) request.result.createObjectStore(name, { keyPath: 'id' }); };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function read<T>(store: string, key?: string): Promise<T> {
  const database = await db();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(store, 'readonly');
    const request = key ? transaction.objectStore(store).get(key) : transaction.objectStore(store).getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function write<T>(store: string, value: T) {
  const database = await db();
  await new Promise<void>((resolve, reject) => {
    const tx = database.transaction(store, 'readwrite');
    tx.objectStore(store).put(value);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error || new Error('Storage transaction aborted'));
  });
  return value;
}
export const storage = {
  projects: () => read<Project[]>('projects'),
  runs: async (projectId: string) => (await read<Run[]>('runs')).filter(r => r.projectId === projectId).sort((a,b) => b.createdAt.localeCompare(a.createdAt)),
  createProject: (name: string) => write<Project>('projects', {id: crypto.randomUUID(), name, createdAt: new Date().toISOString(), baselineHistory: []}),
  saveRun: async (run: Run) => { if (await read<Run | undefined>('runs', run.id)) throw new Error('Existing evidence cannot be replaced. Create a new analysis.'); return write('runs', structuredClone(run)); },
  review: async (run: Run, candidateId: string, value: Review) => {
    const current = await read<Run>('runs', run.id);
    if (!current.analysis.candidates.some(c => c.id === candidateId)) throw new Error('Unknown candidate');
    const oldValue = current.decisions[candidateId] || {decision: 'unreviewed' as const};
    current.events.push({id: crypto.randomUUID(), time: new Date().toISOString(), candidateId, oldValue, newValue: value, modelVersion: current.model.version, runId: current.id, kind: 'review'});
    current.decisions[candidateId] = structuredClone(value);
    current.gate = gateFor(current);
    return write('runs', current);
  },
  undo: async (run: Run) => {
    const current = await read<Run>('runs', run.id);
    const undone = new Set(current.events.map(e => e.undoes).filter(Boolean));
    const event = [...current.events].reverse().find(e => e.kind === 'review' && !undone.has(e.id));
    if (!event) return current;
    current.events.push({id: crypto.randomUUID(), time: new Date().toISOString(), candidateId: event.candidateId, oldValue: current.decisions[event.candidateId], newValue: event.oldValue, modelVersion: current.model.version, runId: current.id, kind: 'undo', undoes: event.id});
    current.decisions[event.candidateId] = event.oldValue;
    current.gate = gateFor(current);
    return write('runs', current);
  },
  baseline: async (project: Project, runId: string, side: 'before' | 'after') => {
    const current = await read<Project>('projects', project.id);
    current.baselineHistory.push({id: crypto.randomUUID(), runId, side, time: new Date().toISOString(), baseline: {runId, side}, old: current.baseline || null, new: {runId, side}});
    current.baseline = {runId, side};
    return write('projects', current);
  },
  importBaseline: async (project: Project, imageUrl: string, sha256: string) => {
    const current = await read<Project>('projects', project.id);
    const baseline: Baseline = {imageId: crypto.randomUUID(), imageUrl, sha256, side: 'before', environment: 'unverified'};
    current.baselineHistory.push({id: crypto.randomUUID(), time: new Date().toISOString(), baseline, old: current.baseline || null, new: baseline});
    current.baseline = baseline;
    return write('projects', current);
  },
  undoBaseline: async (project: Project) => {
    const current = await read<Project>('projects', project.id);
    const undone = new Set(current.baselineHistory.map(e => e.undoOf).filter(Boolean));
    const last = [...current.baselineHistory].reverse().find(e => !e.undoOf && !e.reverted && !undone.has(e.id));
    if (!last) return current;
    const previous = last.old || undefined;
    current.baselineHistory.push({id: crypto.randomUUID(), time: new Date().toISOString(), old: current.baseline || null, new: previous || null, undoOf: last.id});
    current.baseline = previous;
    return write('projects', current);
  },
};
