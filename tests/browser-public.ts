
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const url=new URL(process.argv[2]||'https://yeopbong.github.io/renderguard/');
if(url.protocol!=='https:'&&url.hostname!=='127.0.0.1')throw new Error('Use the HTTPS deployment or loopback test server.');
const output=resolve(process.argv[3]||'artifacts/public-browser.json');
const expected=JSON.parse(await readFile(resolve(root,'web/public/models/manifest.json'),'utf8'));
const browser=await chromium.launch({headless:true});
try{
 const context=await browser.newContext({viewport:{width:1512,height:1050},acceptDownloads:true});const page=await context.newPage();const errors:string[]=[];const requests:{path:string;method:string;origin:string}[]=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});page.on('request',request=>{if(/^https?:/.test(request.url())){const u=new URL(request.url());requests.push({path:u.pathname,method:request.method(),origin:u.origin});}});
 await page.goto(url.href,{waitUntil:'networkidle'});await page.getByRole('button',{name:'Compare screenshots',exact:true}).waitFor();
 const indexResponse=await context.request.get(new URL('examples/index.json',url).href);assert.equal(indexResponse.status(),200);const examples=await indexResponse.json();assert.ok(examples.length>0);
 const beforeResponse=await context.request.get(new URL(`examples/${examples[0].before}`,url).href);const afterResponse=await context.request.get(new URL(`examples/${examples[0].after}`,url).href);assert.equal(beforeResponse.status(),200);assert.equal(afterResponse.status(),200);
 const before=await beforeResponse.body(),after=await afterResponse.body();
 await page.getByRole('button',{name:'Compare screenshots',exact:true}).click();await page.getByLabel('Comparison name',{exact:true}).fill('Public browser verification');await page.getByLabel('Baseline PNG',{exact:true}).setInputFiles({name:'baseline.png',mimeType:'image/png',buffer:before});await page.getByLabel('Current PNG',{exact:true}).setInputFiles({name:'current.png',mimeType:'image/png',buffer:after});await page.getByRole('button',{name:/Analyze comparison/}).click();await page.getByRole('heading',{name:'Changes',exact:true}).waitFor({timeout:120000});
 const saved=()=>page.evaluate(()=>new Promise<any[]>((resolve,reject)=>{const request=indexedDB.open('renderguard-workbench-v1',1);request.onsuccess=()=>{const result=request.result.transaction('runs','readonly').objectStore('runs').getAll();result.onsuccess=()=>resolve(result.result);result.onerror=()=>reject(result.error);};}));
 const initial=(await saved())[0];assert.equal(initial.model.sha256,expected.modelSha256);assert.equal(initial.model.version,expected.version);assert.ok(initial.predictions.length>0);assert.equal(initial.gate.code,1);
 await page.getByRole('button',{name:/Intentional change/}).last().click();await page.locator('.review-state.intentional_change').waitFor();await page.getByRole('button',{name:'Zoom in',exact:true}).click();await page.getByRole('button',{name:'Difference',exact:true}).click();await page.waitForFunction(width=>document.querySelector('canvas')?.width===width,initial.analysis.width);await page.getByRole('button',{name:'Side by side',exact:true}).click();await page.getByLabel('Filter review status').selectOption('intentional_change');assert.equal(await page.locator('.change-item').count(),1);await page.getByLabel('Filter review status').selectOption('all');
 await page.getByText('Export',{exact:true}).click();const event=page.waitForEvent('download');await page.getByRole('button',{name:'Offline HTML report',exact:true}).click();const downloaded=await event;const stream=await downloaded.createReadStream();assert.ok(stream);let html='';for await(const chunk of stream)html+=chunk;assert.ok(html.includes('data:image/png;base64,'));assert.ok(html.includes(initial.model.sha256));
 await page.reload({waitUntil:'networkidle'});await page.getByRole('heading',{name:'Public browser verification',exact:true}).waitFor();const reopened=(await saved())[0];assert.deepEqual(reopened.predictions,initial.predictions);assert.equal(reopened.events.length,1);assert.equal(reopened.decisions[initial.analysis.candidates[0].id].decision,'intentional_change');
 assert.deepEqual(errors,[]);assert.ok(requests.every(r=>r.method==='GET'&&r.origin===url.origin));assert.ok(!requests.some(r=>r.path.includes('/api/')));assert.ok(requests.some(r=>r.path.endsWith('/models/model.onnx')));assert.ok(requests.some(r=>r.path.endsWith('.wasm')));
 await mkdir(dirname(output),{recursive:true});await page.screenshot({path:output.replace(/\.json$/,'.png'),fullPage:true});
 const report={schemaVersion:'1.0',url:url.href,checkedAt:new Date().toISOString(),model:{version:initial.model.version,sha256:initial.model.sha256},execution:'complete',checks:{actualPNGUpload:true,workerCPUInference:true,modelIdentity:true,originalCoordinates:true,zoom:true,rawDifference:true,filter:true,review:true,offlineReportExport:true,refreshPersistence:true,noImageUploads:true,noAPICalls:true,noConsoleErrors:true},candidateCount:initial.analysis.candidates.length,inferenceMs:initial.timing?.inferenceMs,requests:requests.filter((r,i,a)=>a.findIndex(x=>x.path===r.path)===i),errors};await writeFile(output,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({execution:'complete',url:url.href,modelSha256:report.model.sha256,checks:Object.keys(report.checks).length}));await context.close();
}finally{await browser.close();}
