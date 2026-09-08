import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer, type Server } from 'node:http';
import { readFile, readdir, stat, mkdtemp, rm, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { PNG } from 'pngjs';
import { resolve, extname, join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { tmpdir } from 'node:os';
import { chromium, type Browser, type Page } from 'playwright';
import { decodePNG } from '../core/png';
import { analyzePair, tensorsForCandidate, differenceRaster } from '../core/index';
import type { Run } from '../web/src/types';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),dist=join(root,'dist');
let server:Server,browser:Browser,origin:string,temp:string;
const sha=(bytes:Uint8Array)=>createHash('sha256').update(bytes).digest('hex');
let examples:{id:string;title:string;before:string;after:string}[];
const types:Record<string,string>={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.wasm':'application/wasm','.png':'image/png','.json':'application/json','.css':'text/css'};
before(async()=>{
 await stat(join(dist,'index.html'));
 examples=JSON.parse(await readFile(join(dist,'examples/index.json'),'utf8'));
 assert.ok(examples.length>=2,'Actual example PNG pairs must be present');
 temp=await mkdtemp(join(tmpdir(),'renderguard-browser-'));
 server=createServer(async(req,res)=>{try{const pathname=decodeURIComponent(new URL(req.url!,'http://localhost').pathname);if(!pathname.startsWith('/renderguard/')){res.writeHead(404);res.end('Missing');return;}const relative=pathname.slice('/renderguard/'.length)||'index.html';const file=resolve(dist,relative);if(!file.startsWith(dist+'/')){res.writeHead(400);res.end();return;}const bytes=await readFile(file);res.writeHead(200,{'Content-Type':types[extname(file)]||'application/octet-stream','Content-Length':bytes.length,'Cache-Control':'no-store'});res.end(bytes);}catch{res.writeHead(404);res.end('Missing asset');}});
 await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));const address=server.address();assert.ok(address&&typeof address!=='string');origin=`http://127.0.0.1:${address.port}`;
 browser=await chromium.launch({headless:true});
});
after(async()=>{await browser?.close();await new Promise<void>(resolve=>server?.close(()=>resolve()));if(temp)await rm(temp,{recursive:true,force:true});});
async function storedRuns(page:Page):Promise<Run[]>{return page.evaluate(()=>new Promise((resolve,reject)=>{const request=indexedDB.open('renderguard-workbench-v1',1);request.onsuccess=()=>{const tx=request.result.transaction('runs','readonly');const result=tx.objectStore('runs').getAll();result.onsuccess=()=>resolve(result.result);result.onerror=()=>reject(result.error);};request.onerror=()=>reject(request.error);}));}
async function waitRun(page:Page){await page.getByRole('heading',{name:'Changes',exact:true}).waitFor({timeout:120000});await page.locator('.progress-panel').waitFor({state:'hidden'});}
async function startSample(page:Page){await page.goto(`${origin}/renderguard/`);await page.getByRole('button',{name:/Try a real example/}).click();await waitRun(page);}

test('browser WASM shares exact PNG bytes, candidates and tensor preprocessing with Node', {timeout:120000}, async()=>{
 const context=await browser.newContext();const page=await context.newPage();await page.goto(`${origin}/renderguard/`);
 const workerFile=(await readdir(join(dist,'assets'))).find(n=>n.startsWith('inference.worker-')&&n.endsWith('.js'));assert.ok(workerFile);
 const sample=examples[0];const result=await page.evaluate(async({base,workerFile,sample})=>{
  const [before,after]=await Promise.all([fetch(`${base}examples/${sample.before}`).then(r=>r.blob()),fetch(`${base}examples/${sample.after}`).then(r=>r.blob())]);
  return new Promise<any>((resolve,reject)=>{const worker=new Worker(`${base}assets/${workerFile}`,{type:'module'});worker.onerror=e=>reject(new Error(e.message));worker.onmessage=e=>{if(e.data.type==='error'){worker.terminate();reject(new Error(e.data.error));}if(e.data.type==='result'){worker.terminate();resolve(e.data);}};worker.postMessage({base,before,after,masks:[],diagnostics:true});});
 },{base:`${origin}/renderguard/`,workerFile,sample});
 const before=decodePNG(await readFile(join(dist,'examples',sample.before))),after=decodePNG(await readFile(join(dist,'examples',sample.after)));const expected=analyzePair(before,after,[]);
 assert.deepEqual(result.analysis,expected);assert.equal(result.trace.rasterBeforeSHA256,sha(new Uint8Array(before.data)));assert.equal(result.trace.rasterAfterSHA256,sha(new Uint8Array(after.data)));assert.ok(expected.candidates.length>0);
 for(const candidate of expected.candidates){const tensor=tensorsForCandidate(before,after,candidate);const arrays=[tensor.localBefore,tensor.localAfter,tensor.contextBefore,tensor.contextAfter,tensor.geometry];const floats=new Float32Array(arrays.reduce((n,v)=>n+v.length,0));let offset=0;for(const a of arrays){floats.set(a,offset);offset+=a.length;}assert.equal(result.trace.tensorSHA256s.find((t:any)=>t.candidateId===candidate.id).sha256,sha(new Uint8Array(floats.buffer)));}
 const manifest=JSON.parse(await readFile(join(dist,'models/manifest.json'),'utf8'));assert.equal(result.model.sha256,sha(await readFile(join(dist,'models/model.onnx'))));assert.equal(result.model.version,manifest.version);assert.equal(result.predictions.length,expected.candidates.length);for(const prediction of result.predictions)assert.ok(prediction.logits.every(Number.isFinite));
 const parityFile=join(dist,'models/parity.json');
 assert.notEqual(manifest.version,'preflight-only','Release tests require a trained model');
 {
  const parity=JSON.parse(await readFile(parityFile,'utf8'));assert.equal(parity.modelSha256,result.model.sha256);assert.equal(parity.before,`examples/${sample.before}`);assert.equal(parity.after,`examples/${sample.after}`);
  let maxLogitError=0,maxScoreError=0,logitZeroDifferences=0,thresholdDifferences=0;
  for(const p of parity.predictions){const actual=result.predictions.find((r:any)=>r.candidateId===p.candidateId);assert.ok(actual);for(let k=0;k<5;k++){maxLogitError=Math.max(maxLogitError,Math.abs(p.logits[k]-actual.logits[k]));maxScoreError=Math.max(maxScoreError,Math.abs(p.scores[k]-actual.scores[k]));if((p.logits[k]>=0)!==(actual.logits[k]>=0))logitZeroDifferences++;if((p.scores[k]>=manifest.thresholds[k])!==(actual.scores[k]>=manifest.thresholds[k]))thresholdDifferences++;}p.logits.forEach((value:number,k:number)=>assert.ok(Math.abs(value-actual.logits[k])<1e-4,`ONNX/browser logit mismatch: ${value} versus ${actual.logits[k]}`));p.scores.forEach((value:number,k:number)=>assert.ok(Math.abs(value-actual.scores[k])<1e-4));}
  const artifactDirectory=process.env.RENDERGUARD_TEST_ARTIFACT_DIR||join(root,'artifacts');await mkdir(artifactDirectory,{recursive:true});const calibrationSha256=sha(await readFile(join(dist,'models/calibration.json')));assert.equal(calibrationSha256,manifest.calibrationSha256);await writeFile(join(artifactDirectory,'browser-parity.json'),JSON.stringify({schemaVersion:'1.0',checkedAt:new Date().toISOString(),browser:browser.version(),execution:'complete',modelSha256:result.model.sha256,calibrationSha256,preprocessVersion:result.model.preprocessVersion,sampleId:sample.id,candidateCount:result.analysis.candidates.length,reference:'Published shared-tensor ONNX Runtime fixture in models/parity.json',exactDecodedRasterHashes:result.trace,exactCandidateEquality:true,maxAbsoluteLogitError:maxLogitError,maxAbsoluteScoreError:maxScoreError,logitZeroDecisionDifferences:logitZeroDifferences,publishedThresholdDecisionDifferences:thresholdDifferences,tolerance:1e-4},null,2)+'\n');
 }
 await context.close();
});

test('real PNG upload, review labels, undo, baseline history, persistence and standalone report', {timeout:120000}, async()=>{
 const context=await browser.newContext({viewport:{width:1512,height:1040},acceptDownloads:true});const page=await context.newPage();const errors:string[]=[],requests:{url:string;method:string}[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});page.on('request',r=>requests.push({url:r.url(),method:r.method()}));
 await page.goto(`${origin}/renderguard/`);await page.getByRole('button',{name:'Compare screenshots',exact:true}).click();await page.getByLabel('Baseline PNG',{exact:true}).setInputFiles(join(dist,'examples',examples[0].before));await page.getByLabel('Current PNG',{exact:true}).setInputFiles(join(dist,'examples',examples[0].after));await page.getByRole('button',{name:/Analyze comparison/}).click();await waitRun(page);
 const original=(await storedRuns(page))[0];assert.equal(original.execution,'complete');assert.equal(original.environment,'unverified');assert.equal(original.gate.code,1);assert.ok(original.analysis.candidates.length>0);const immutable=JSON.stringify(original.predictions);
 await page.getByRole('button',{name:/Intentional change/}).last().click();await page.waitForFunction(()=>document.querySelector('.review-state.intentional_change')!==null);let saved=(await storedRuns(page))[0];assert.equal(JSON.stringify(saved.predictions),immutable);assert.equal(saved.events.length,1);assert.equal(saved.decisions[saved.analysis.candidates[0].id].decision,'intentional_change');
 await page.getByText('Correct observation labels',{exact:false}).click();await page.getByLabel('Correct Layout displacement observation',{exact:true}).selectOption('yes');await page.waitForFunction(()=>document.querySelector('.workbench-footer')?.textContent?.includes('2 review events'));saved=(await storedRuns(page))[0];assert.equal(saved.decisions[saved.analysis.candidates[0].id].observation?.layout_displacement,true);assert.equal(JSON.stringify(saved.predictions),immutable);
 await page.getByRole('button',{name:'Undo last review',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.workbench-footer')?.textContent?.includes('3 review events'));saved=(await storedRuns(page))[0];assert.equal(saved.decisions[saved.analysis.candidates[0].id].observation?.layout_displacement,undefined);assert.equal(saved.decisions[saved.analysis.candidates[0].id].decision,'intentional_change');
 await page.evaluate(()=>{if(document.activeElement instanceof HTMLElement)document.activeElement.blur();});await page.keyboard.press('3');await page.locator('.review-state.uncertain').waitFor();await page.keyboard.press('z');await page.locator('.review-state.intentional_change').waitFor();assert.equal((await storedRuns(page))[0].events.length,5);
 await page.getByText('Review priority settings',{exact:true}).click();await page.getByLabel('Layout displacement priority weight').selectOption('2');assert.equal(JSON.stringify((await storedRuns(page))[0].predictions),immutable);await page.getByText('Review priority settings',{exact:true}).click();
 const oldZoom=await page.locator('.zoom-controls output').innerText();await page.getByRole('button',{name:'Zoom in',exact:true}).click();assert.notEqual(await page.locator('.zoom-controls output').innerText(),oldZoom);assert.equal(await page.getByRole('button',{name:/Locate region 1/}).count(),2);await page.getByRole('button',{name:'Overlay',exact:true}).click();await page.getByLabel('Overlay opacity').fill('0.7');await page.getByRole('button',{name:'Difference',exact:true}).click();await page.getByLabel('Raw pixel difference image').waitFor();await page.waitForFunction(width=>(document.querySelector('canvas')?.width===width),original.analysis.width);const rasterDigest=await page.locator('canvas').evaluate(async canvas=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',(canvas as HTMLCanvasElement).getContext('2d')!.getImageData(0,0,(canvas as HTMLCanvasElement).width,(canvas as HTMLCanvasElement).height).data)),v=>v.toString(16).padStart(2,'0')).join(''));const rawDifference=differenceRaster(decodePNG(await readFile(join(dist,'examples',examples[0].before))),decodePNG(await readFile(join(dist,'examples',examples[0].after))));assert.equal(rasterDigest,sha(new Uint8Array(rawDifference.data)));await page.getByRole('button',{name:'Side by side',exact:true}).click();
 await page.getByLabel('Filter review status').selectOption('unreviewed');assert.equal(await page.locator('.change-item').count(),original.analysis.candidates.length-1);await page.getByLabel('Filter review status').selectOption('all');await page.getByRole('button',{name:'Use current as baseline'}).click();await page.getByRole('button',{name:'Project history',exact:true}).click();assert.equal(await page.locator('.baseline-row').count(),1);await page.getByRole('button',{name:'Restore previous baseline'}).click();await page.getByText('Reverted',{exact:true}).waitFor();await page.locator('.history-list>button').first().click();
 await page.reload();await waitRun(page);saved=(await storedRuns(page))[0];assert.equal(saved.id,original.id);assert.equal(JSON.stringify(saved.predictions),immutable);assert.equal(saved.events.length,5);
 await page.getByText('Export',{exact:true}).click();const downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'Offline HTML report'}).click();const report=await downloadEvent;const reportPath=join(temp,'report.html');await report.saveAs(reportPath);const html=await readFile(reportPath,'utf8');assert.ok(html.includes('data:image/png;base64,'));assert.ok(html.includes('intentional_change'));assert.ok(!html.includes('<script src='));
 const offline=await context.newPage();const offlineRequests:string[]=[];offline.on('request',r=>{if(/^https?:/.test(r.url()))offlineRequests.push(r.url());});await offline.goto(pathToFileURL(reportPath).href);await offline.getByRole('heading',{name:'Original screenshots'}).waitFor();assert.equal(await offline.locator('img').count(),2);assert.ok(await offline.locator('img').evaluateAll(images=>images.every(i=>(i as HTMLImageElement).naturalWidth>0)));assert.deepEqual(offlineRequests,[]);await offline.close();
 assert.deepEqual(errors,[]);assert.ok(requests.every(r=>r.method==='GET'));assert.ok(requests.every(r=>r.url.startsWith(origin)||r.url.startsWith('data:')||r.url.startsWith('blob:')));assert.ok(requests.some(r=>r.url.endsWith('model.onnx')));assert.ok(requests.some(r=>r.url.endsWith('.wasm')));assert.ok(!requests.some(r=>r.url.includes('/api/')));
 await page.screenshot({path:join(temp,'workbench.png'),fullPage:true});await context.close();
});

test('baseline-only import produces no regression pass; subsequent analysis gets fresh decisions', {timeout:120000}, async()=>{
 const context=await browser.newContext();const page=await context.newPage();await page.goto(`${origin}/renderguard/`);await page.getByRole('button',{name:'Compare screenshots',exact:true}).click();await page.getByLabel('Image workflow').selectOption('baseline');await page.getByLabel('Baseline PNG',{exact:true}).setInputFiles(join(dist,'examples',examples[0].before));await page.getByRole('button',{name:'Save baseline',exact:true}).click();await page.getByText(/Baseline saved. No regression analysis has been performed/).waitFor();assert.equal((await storedRuns(page)).length,0);
 await page.getByRole('button',{name:'New comparison',exact:true}).click();await page.getByLabel('Image workflow').selectOption('saved');await page.getByLabel('Current PNG',{exact:true}).setInputFiles(join(dist,'examples',examples[0].after));await page.getByRole('button',{name:/Analyze comparison/}).click();await waitRun(page);const run=(await storedRuns(page))[0];assert.equal(run.gate.code,1);assert.deepEqual(run.decisions,{});assert.deepEqual(run.events,[]);
 await context.close();
});


test('multiple genuine change regions retain score ordering and severity sorting; stable long pages stay unverified', {timeout:120000}, async()=>{
 const context=await browser.newContext();const page=await context.newPage();
 const images=await Promise.all([examples[0].before,examples[0].after,examples[4].before,examples[4].after].map(async name=>decodePNG(await readFile(join(dist,'examples',name)))));
 const width=images[0].width,offset=images[0].height+240,height=offset+Math.max(images[2].height,images[3].height);
 function combine(first:typeof images[0],second:typeof images[0]){const image=new PNG({width,height});image.data.fill(255);for(const [source,y0] of [[first,0],[second,offset]] as const)for(let y=0;y<source.height;y++)image.data.set(source.data.subarray(y*width*4,(y+1)*width*4),(y+y0)*width*4);return PNG.sync.write(image);}
 await page.goto(`${origin}/renderguard/`);await page.getByRole('button',{name:'Compare screenshots',exact:true}).click();await page.getByLabel('Baseline PNG',{exact:true}).setInputFiles({name:'two-regions-before.png',mimeType:'image/png',buffer:combine(images[0],images[2])});await page.getByLabel('Current PNG',{exact:true}).setInputFiles({name:'two-regions-after.png',mimeType:'image/png',buffer:combine(images[1],images[3])});await page.getByRole('button',{name:/Analyze comparison/}).click();await waitRun(page);
 const saved=(await storedRuns(page))[0];assert.ok(saved.analysis.candidates.length>=2,'Sorting must be tested with multiple independently inferred regions');assert.ok(saved.analysis.height>1500);
 const expectedOrder=(weights:number[])=>[...saved.analysis.candidates].sort((a,b)=>{const score=(c:typeof a)=>{const p=saved.predictions.find(p=>p.candidateId===c.id)!;return Math.max(...p.scores.map((score,i)=>score*weights[i]))+.05*Math.min(1,c.changedPixels/(saved.analysis.width*saved.analysis.height));};return score(b)-score(a)||b.changedPixels-a.changedPixels;}).map(c=>c.id);
 assert.deepEqual(await page.locator('.change-item').evaluateAll(items=>items.map(item=>item.getAttribute('data-candidate-id'))),expectedOrder([1,1,1,1,1]));
 await page.getByText('Review priority settings',{exact:true}).click();await page.getByLabel('Overlap / occlusion priority weight',{exact:true}).selectOption('2');await page.getByLabel('Element disappearance priority weight',{exact:true}).selectOption('0.5');assert.deepEqual(await page.locator('.change-item').evaluateAll(items=>items.map(item=>item.getAttribute('data-candidate-id'))),expectedOrder([1,2,1,.5,1]));assert.deepEqual((await storedRuns(page))[0].predictions,saved.predictions);assert.equal((await storedRuns(page))[0].gate.code,1);
 await context.close();
 const stableContext=await browser.newContext();const stable=await stableContext.newPage();await stable.goto(`${origin}/renderguard/`);await stable.getByRole('button',{name:/A stable long page/}).click();await waitRun(stable);const unchanged=(await storedRuns(stable))[0];assert.ok(unchanged.analysis.height>900);assert.equal(unchanged.analysis.candidates.length,0);assert.equal(unchanged.analysis.changedPixels,0);assert.equal(unchanged.predictions.length,0);assert.equal(unchanged.execution,'complete');assert.equal(unchanged.gate.code,0);assert.equal(unchanged.environment,'unverified');await stable.getByText('No pixel changes',{exact:true}).waitFor();await stableContext.close();
});

test('missing model and cancellation are failures, never no-change results', {timeout:120000}, async()=>{
 const context=await browser.newContext();const page=await context.newPage();await page.route('**/models/model.onnx',route=>route.fulfill({status:503,body:'Unavailable'}));await page.goto(`${origin}/renderguard/`);await page.getByRole('button',{name:/Try a real example/}).click();await page.getByRole('alert').filter({hasText:'Model download failed (503)'}).waitFor({timeout:30000});assert.equal((await storedRuns(page)).length,0);assert.equal(await page.getByRole('heading',{name:'Changes',exact:true}).count(),0);
 await page.unroute('**/models/model.onnx');await page.route('**/models/calibration.json',route=>route.fulfill({status:200,contentType:'application/json',body:'{"classes":[]}'}));await page.getByRole('button',{name:/Try a real example/}).click();await page.getByRole('alert').filter({hasText:'Calibration integrity check failed'}).waitFor({timeout:30000});assert.equal((await storedRuns(page)).length,0);await page.unroute('**/models/calibration.json');await page.route('**/models/model.onnx',async route=>{await new Promise(r=>setTimeout(r,2500));try{await route.continue();}catch{}});await page.getByRole('button',{name:/Try a real example/}).click();await page.getByText('Downloading visual model',{exact:true}).waitFor({timeout:15000});await page.getByRole('button',{name:'Cancel',exact:true}).click();await page.getByRole('alert').filter({hasText:'Analysis cancelled'}).waitFor();await page.waitForTimeout(2800);assert.equal((await storedRuns(page)).length,0);await context.close();
});

test('saved reports recompute stale gates and show incomplete evidence without crashing', {timeout:120000}, async()=>{
 const context=await browser.newContext({acceptDownloads:true});
 const page=await context.newPage();const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await startSample(page);
  const original=(await storedRuns(page))[0];
  async function save(value:unknown){await page.evaluate(value=>new Promise<void>((resolve,reject)=>{const request=indexedDB.open('renderguard-workbench-v1',1);request.onsuccess=()=>{const tx=request.result.transaction('runs','readwrite');tx.objectStore('runs').put(value);tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);};request.onerror=()=>reject(request.error);}),value);await page.reload();}
  const incomplete=structuredClone(original) as Partial<Run>;delete incomplete.analysis;incomplete.gate={code:0,reason:'Outdated result'};
  await save(incomplete);await page.getByRole('heading',{name:'Analysis incomplete.',exact:true}).waitFor();
  const downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'Export execution evidence'}).click();
  const download=await downloadEvent;const path=join(temp,'incomplete.json');await download.saveAs(path);assert.equal(JSON.parse(await readFile(path,'utf8')).gate.code,3);
  const valid=structuredClone(original) as Partial<Run>;delete valid.contracts;delete valid.events;valid.gate={code:0,reason:'Outdated result'};
  await save(valid);await waitRun(page);assert.equal(await page.locator('.failure-page').count(),0);
  await page.getByText('Export',{exact:true}).click();const jsonEvent=page.waitForEvent('download');await page.getByRole('button',{name:'Versioned JSON evidence'}).click();const jsonDownload=await jsonEvent;const jsonPath=join(temp,'unreviewed.json');await jsonDownload.saveAs(jsonPath);assert.equal(JSON.parse(await readFile(jsonPath,'utf8')).gate.code,1);
  assert.deepEqual(errors,[]);
 }finally{await context.close();}
});
