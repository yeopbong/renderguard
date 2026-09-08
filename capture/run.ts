import { chromium, type Page } from 'playwright';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { mkdir } from 'node:fs/promises';
import { LIMITS, InputError, validateMasks, differenceRaster, analyzePair, type Mask, type Raster } from '../core/index.ts';
import { atomicWrite, decodePng, writePng, maskedRaster } from './png.ts';
import { evaluateContracts, type Contract } from './contracts.ts';
import { assertAllowedTarget, normalizedOrigin, type TargetPolicy } from './security.ts';
export type CaptureConfig = { beforeUrl: string; afterUrl: string; outputDir: string; viewport: { width: number; height: number }; deviceScaleFactor?: number; readySelector?: string; masks?: Mask[]; contracts?: Contract[]; allowedTargets?: string[]; deniedOrigins?: string[]; deniedPorts?: number[]; timeoutMs?: number; state?: { locale?: string; timezoneId?: string; colorScheme?: 'light' | 'dark'; fixedTime?: number; randomSeed?: number } };
export type CaptureProgress = { stage: string; completed: number; total: number };
const sha256 = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
async function settle(page: Page, readySelector: string | undefined, timeout: number): Promise<void> {
  if (readySelector) await page.locator(readySelector).waitFor({ state: 'visible', timeout });
  await page.evaluate(async maximum => {
    let timeoutId: ReturnType<typeof setTimeout>;
    const timeout = new Promise<never>((_, reject) => { timeoutId = setTimeout(() => reject(new Error('Fonts or visible images did not become ready.')), maximum); });
    try {
      await Promise.race([Promise.all([document.fonts.ready, ...Array.from(document.images).filter(img => { const r = img.getBoundingClientRect(); return r.width > 0 && r.height > 0; }).map(async img => { if (!img.complete) await new Promise<void>((resolve, reject) => { img.addEventListener('load', () => resolve(), { once: true }); img.addEventListener('error', () => reject(new Error('An image failed to load.')), { once: true }); }); if (img.naturalWidth === 0) throw new Error('An image failed to decode.'); if (img.decode) await img.decode(); })]), timeout]);
    } finally { clearTimeout(timeoutId!); }
    window.scrollTo(0, 0);
  }, timeout);
}
export async function capturePair(config: CaptureConfig, progress: (event: CaptureProgress) => void = () => {}): Promise<Record<string, unknown>> {
  if (!config.outputDir) throw new InputError('An output directory is required.');
  if (!Number.isInteger(config.viewport?.width) || !Number.isInteger(config.viewport?.height) || config.viewport.width < 240 || config.viewport.width > LIMITS.maxWidth || config.viewport.height < 200 || config.viewport.height > 2160) throw new InputError('Viewport must be 240–4096 CSS pixels wide and 200–2160 CSS pixels high.');
  const dpr = config.deviceScaleFactor ?? 1;
  if (![1, 2].includes(dpr)) throw new InputError('Supported device scale factors are 1 and 2. Screenshots are captured at CSS scale.');
  const timeout = config.timeoutMs ?? 15000;
  if (!Number.isFinite(timeout) || timeout < 1000 || timeout > 60000) throw new InputError('Timeout must be between 1000 and 60000 milliseconds.');
  const masks = validateMasks(config.masks ?? []), policy: TargetPolicy = { allowedTargets: config.allowedTargets ?? [normalizedOrigin(config.beforeUrl), normalizedOrigin(config.afterUrl)], deniedOrigins: config.deniedOrigins, deniedPorts: config.deniedPorts };
  assertAllowedTarget(config.beforeUrl, policy); assertAllowedTarget(config.afterUrl, policy);
  if ((config.contracts?.length ?? 0) > 100) throw new InputError('At most 100 explicit contracts are supported.');
  await mkdir(config.outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true }), results: Record<string, any>[] = [];
  const locale = config.state?.locale ?? 'en-US', timezoneId = config.state?.timezoneId ?? 'UTC', colorScheme = config.state?.colorScheme ?? 'light';
  let stage = 'launch';
  try {
    for (const [side, url] of [['before', config.beforeUrl], ['after', config.afterUrl]] as const) {
      const blockedRequests: { url: string; reason: string }[] = [];
      const context = await browser.newContext({ viewport: config.viewport, deviceScaleFactor: dpr, locale, timezoneId, colorScheme, reducedMotion: 'reduce', serviceWorkers: 'block', acceptDownloads: false });
      try {
        await context.route('**/*', async route => {
          const request = route.request();
          try { assertAllowedTarget(request.url(), policy); if (!['GET', 'HEAD'].includes(request.method())) throw new InputError('Capture permits read-only network requests.'); await route.continue(); }
          catch (error) { blockedRequests.push({ url: request.url().split('?')[0].slice(0, 500), reason: error instanceof Error ? error.message : 'Blocked request.' }); await route.abort('blockedbyclient'); }
        });
        await context.routeWebSocket('**/*', socket => { blockedRequests.push({ url: socket.url().split('?')[0].slice(0, 500), reason: 'WebSocket traffic is disabled during capture.' }); socket.close(); });
        await context.addInitScript(({ fixedTime, randomSeed }) => {
          if (typeof fixedTime === 'number') {
            const NativeDate = Date, timeValue = fixedTime;
            const FrozenDate = class extends NativeDate { constructor(...args: any[]) { if (!args.length) super(timeValue); else if (args.length === 1) super(args[0]); else super(args[0], args[1], args[2] ?? 1, args[3] ?? 0, args[4] ?? 0, args[5] ?? 0, args[6] ?? 0); } static now() { return timeValue; } };
            window.Date = FrozenDate as DateConstructor;
          }
          if (typeof randomSeed === 'number') { let seed = randomSeed >>> 0; Math.random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; }; }
        }, { fixedTime: config.state?.fixedTime, randomSeed: config.state?.randomSeed });
        const page = await context.newPage(); page.setDefaultTimeout(timeout); page.setDefaultNavigationTimeout(timeout);
        stage = `${side}:navigate`; progress({ stage, completed: results.length, total: 2 });
        const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout });
        if (!response?.ok()) throw new InputError(`Navigation failed with HTTP status ${response?.status() ?? 'unavailable'}.`);
        assertAllowedTarget(page.url(), policy);
        stage = `${side}:ready`; progress({ stage, completed: results.length, total: 2 });
        await page.addStyleTag({ content: '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}html{scroll-behavior:auto!important}' });
        await settle(page, config.readySelector, timeout);
        const dimensions = await page.evaluate(() => ({ width: Math.max(document.documentElement.scrollWidth, document.documentElement.clientWidth), height: Math.max(document.documentElement.scrollHeight, document.documentElement.clientHeight), devicePixelRatio: window.devicePixelRatio, fontsStatus: document.fonts.status }));
        if (dimensions.width > LIMITS.maxWidth || dimensions.height > LIMITS.maxHeight || dimensions.width * dimensions.height > LIMITS.maxPixels) throw new InputError('Full-page screenshot exceeds resource limits. Partition the target.');
        if (blockedRequests.some(request => !request.reason.startsWith('WebSocket'))) throw new InputError('A required network request was blocked by the development target policy.');
        stage = `${side}:contracts`; const contracts = await evaluateContracts(page, config.contracts ?? []);
        stage = `${side}:screenshot`; const bytes = await page.screenshot({ fullPage: true, type: 'png', animations: 'disabled', caret: 'hide', scale: 'css', timeout });
        const repeated = await page.screenshot({ fullPage: true, type: 'png', animations: 'disabled', caret: 'hide', scale: 'css', timeout });
        const raster = decodePng(bytes), stableUnderMasks = analyzePair(raster, decodePng(repeated), masks).changedPixels === 0, path = join(config.outputDir, `${side}.png`);
        await atomicWrite(path, bytes); await writePng(join(config.outputDir, `analysis-${side}.png`), maskedRaster(raster, masks));
        results.push({ side, url: page.url(), screenshot: `${side}.png`, sha256: sha256(bytes), repeatedSha256: sha256(repeated), stable: sha256(bytes) === sha256(repeated), stableUnderMasks, viewport: config.viewport, deviceScaleFactor: dpr, actualDevicePixelRatio: dimensions.devicePixelRatio, screenshotScale: 'css', cssToImageScale: 1, browser: browser.version(), locale, timezoneId, colorScheme, fontsReady: dimensions.fontsStatus === 'loaded', pageSize: { width: dimensions.width, height: dimensions.height }, imageSize: { width: raster.width, height: raster.height }, masks, state: { readySelector: config.readySelector ?? null, fixedTime: config.state?.fixedTime ?? null, randomSeed: config.state?.randomSeed ?? null, animationPolicy: 'CSS animation and transition disabled; JavaScript timers are not universally frozen.' }, blockedRequests, contracts });
        progress({ stage: `${side}:saved`, completed: results.length, total: 2 });
      } finally { await context.close(); }
    }
    const [before, after] = results, comparable = before.imageSize.width === after.imageSize.width && before.actualDevicePixelRatio === after.actualDevicePixelRatio && before.browser === after.browser && before.fontsReady && after.fontsReady && before.stableUnderMasks && after.stableUnderMasks;
    const warnings = results.flatMap(r => [!r.stableUnderMasks ? `${r.side}: repeated captures differ. Configure explicit readiness or declared masks; dynamic content is not fully frozen.` : null, r.blockedRequests.length ? `${r.side}: network requests were blocked by the development target policy.` : null].filter(Boolean));
    const contracts = (config.contracts ?? []).map((contract, i) => ({ ...after.contracts[i], id: contract.id ?? `contract-${i + 1}`, before: before.contracts[i], after: after.contracts[i] }));
    const result = { schemaVersion: '1.0', execution: comparable ? 'complete' : 'incomparable', environment: 'verified', before, after, contracts, masks, warnings, manifestPath: 'manifest.json' };
    await atomicWrite(join(config.outputDir, 'manifest.json'), JSON.stringify(result, null, 2));
    if (comparable) {
      const { readPng } = await import('./png.ts'); const [a, b] = await Promise.all([readPng(join(config.outputDir, 'before.png')), readPng(join(config.outputDir, 'after.png'))]);
      await writePng(join(config.outputDir, 'diff.png'), differenceRaster(a, b, masks));
    }
    return result;
  } catch (error) {
    await atomicWrite(join(config.outputDir, 'failure.json'), JSON.stringify({ execution: 'error', stage, message: error instanceof Error ? error.message : String(error), completed: results }, null, 2));
    throw error;
  } finally { await browser.close(); }
}
