import type { Page } from 'playwright';
import type { Rect } from '../core/index.ts';
export type Contract = { id?: string; type: 'required-visible' | 'inside-container' | 'non-overlap'; selector: string; container?: string; other?: string; tolerance?: number; required?: boolean };
export type Measurement = { selector: string; matches: number; box?: Rect; displayed?: boolean; inPage?: boolean; role?: string; parentTag?: string; reason?: string };
export type ContractResult = Contract & { status: 'satisfied' | 'violated' | 'inconclusive' | 'error'; reason: string; measurements: Measurement[]; coordinateSpace: 'document-css-pixels'; scope: string };
export async function measureElement(page: Page, selector: string): Promise<Measurement> {
  try {
    const matches = await page.locator(selector).count();
    if (matches !== 1) return { selector, matches, reason: matches ? 'Selector matches multiple elements.' : 'Element was not found.' };
    return await page.locator(selector).evaluate((element, suppliedSelector) => {
      const r = element.getBoundingClientRect(), style = getComputedStyle(element);
      let displayed = r.width > 0 && r.height > 0 && element.getClientRects().length > 0;
      for (let node: Element | null = element; node; node = node.parentElement) {
        const s = getComputedStyle(node);
        if (s.display === 'none' || s.visibility === 'hidden' || s.visibility === 'collapse' || Number(s.opacity) <= 0) displayed = false;
      }
      const width = Math.max(document.documentElement.scrollWidth, document.documentElement.clientWidth), height = Math.max(document.documentElement.scrollHeight, document.documentElement.clientHeight);
      const box = { x: r.x + window.scrollX, y: r.y + window.scrollY, width: r.width, height: r.height };
      return { selector: suppliedSelector, matches: 1, box, displayed, inPage: box.x + box.width > 0 && box.y + box.height > 0 && box.x < width && box.y < height, role: element.getAttribute('role') ?? element.tagName.toLowerCase(), parentTag: element.parentElement?.tagName.toLowerCase(), reason: style.transform !== 'none' ? 'Axis-aligned geometry includes CSS transforms.' : undefined };
    }, selector);
  } catch (error) { return { selector, matches: 0, reason: error instanceof Error ? error.message.slice(0, 300) : 'Element could not be measured.' }; }
}
export function evaluateGeometry(contract: Contract, measurements: Measurement[]): ContractResult {
  const base = { ...contract, measurements, coordinateSpace: 'document-css-pixels' as const, scope: 'Axis-aligned rendered boxes and computed visibility; does not prove clickability or pixel occlusion.' };
  const tolerance = contract.tolerance ?? 1;
  if (!Number.isFinite(tolerance) || tolerance < 0 || tolerance > 100) return { ...base, status: 'error', reason: 'Tolerance must be between 0 and 100 CSS pixels.' };
  if (measurements.some(m => m.matches !== 1 || !m.box || !Object.values(m.box).every(Number.isFinite))) return { ...base, status: 'inconclusive', reason: 'Each selector must resolve to one measurable element.' };
  const first = measurements[0];
  if (contract.type === 'required-visible') {
    if (!first.displayed || !first.inPage) return { ...base, status: 'violated', reason: 'The element has no visible nonzero layout box within the page.' };
    return { ...base, status: 'satisfied', reason: 'The element has a rendered layout box within the page; actual occlusion and interaction are outside this contract.' };
  }
  if (measurements.length !== 2 || measurements.some(m => !m.displayed || !m.box || m.box.width <= 0 || m.box.height <= 0)) return { ...base, status: 'inconclusive', reason: 'Both elements need nonzero rendered boxes for this geometric measurement.' };
  const a = first.box!, b = measurements[1].box!;
  if (contract.type === 'inside-container') {
    const satisfied = a.x >= b.x - tolerance && a.y >= b.y - tolerance && a.x + a.width <= b.x + b.width + tolerance && a.y + a.height <= b.y + b.height + tolerance;
    return { ...base, status: satisfied ? 'satisfied' : 'violated', reason: satisfied ? 'The element border box is inside the container border box within tolerance.' : 'The element border box exceeds the declared container border box.' };
  }
  if (contract.type === 'non-overlap') {
    const overlapX = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x), overlapY = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
    const violated = overlapX > tolerance && overlapY > tolerance;
    return { ...base, status: violated ? 'violated' : 'satisfied', reason: violated ? 'The declared border boxes overlap beyond tolerance; this is geometric overlap, not proof of occlusion.' : 'The declared border boxes do not overlap beyond tolerance.' };
  }
  return { ...base, status: 'error', reason: 'Unsupported contract type.' };
}
export async function evaluateContracts(page: Page, contracts: Contract[]): Promise<ContractResult[]> {
  const results: ContractResult[] = [];
  for (const contract of contracts) {
    const selectors = [contract.selector];
    if (contract.type === 'inside-container') selectors.push(contract.container ?? '');
    if (contract.type === 'non-overlap') selectors.push(contract.other ?? '');
    const measurements = await Promise.all(selectors.map(selector => selector ? measureElement(page, selector) : Promise.resolve({ selector, matches: 0, reason: 'Second selector is required.' })));
    results.push(evaluateGeometry(contract, measurements));
  }
  return results;
}
