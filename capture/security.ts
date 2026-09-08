import { InputError } from '../core/index.ts';
export type TargetPolicy = { allowedTargets: string[]; deniedOrigins?: string[]; deniedPorts?: number[] };
export function normalizedOrigin(value: string): string {
  let url: URL; try { url = new URL(value); } catch { throw new InputError('Target URL is invalid.'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new InputError('Targets must use HTTP(S) without embedded credentials.');
  if (!['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) throw new InputError('Only explicitly allowed loopback development targets are supported.');
  return url.origin;
}
export function assertAllowedTarget(value: string, policy: TargetPolicy): URL {
  const origin = normalizedOrigin(value), url = new URL(value), allowed = policy.allowedTargets.map(normalizedOrigin);
  if (!allowed.includes(origin)) throw new InputError('Target origin is not in the explicit development allowlist.');
  const port = Number(url.port || (url.protocol === 'https:' ? 443 : 80));
  if (policy.deniedOrigins?.includes(origin) || (policy.deniedPorts ?? [8765]).includes(port)) throw new InputError('The workbench service or a denied origin cannot be captured.');
  return url;
}
