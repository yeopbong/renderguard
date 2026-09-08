import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {chromium} from 'playwright';
import {PNG} from 'pngjs';
import {families,pageHTML,operations,mutate,mutationScript} from './scenes.mjs';
import {establish} from './verify.mjs';
import {renderSettled} from './render.mjs';
const root=process.cwd(),out=path.join(root,'data');
const args=new Set(process.argv.slice(2));const pilot=args.has('--pilot');
const selected=pilot?families.slice(0,2):families;
await fs.mkdir(out,{recursive:true});await fs.mkdir('artifacts',{recursive:true});
const grouping={version:'original-24-v2',license:'CC0-1.0',createdBeforeRendering:true,families,sharedComponents:['base-css-v2'],note:'Original synthetic structures, not independent real websites.'};
await fs.writeFile('artifacts/groups.json',JSON.stringify(grouping,null,2));
const start=performance.now();const browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
const records=[];const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
for(const family of selected){
 for(let variant=0;variant<(pilot?2:6);variant++){
  const viewport={width:variant%3===2?390:900,height:760};
  const context=await browser.newContext({viewport,deviceScaleFactor:1,locale:'en-US',timezoneId:'UTC',colorScheme:'light'});const page=await context.newPage();
  const html=pageHTML(family,variant);await page.setContent(html);await page.evaluate(()=>document.fonts.ready);
  const beforeRender=await renderSettled(page,viewport),beforeInspect=beforeRender.observations,beforeBuf=beforeRender.buffer,beforePng=beforeRender.png;
  const beforePath=`${family.id}-${variant}-before.png`;await fs.writeFile(path.join(out,beforePath),beforeBuf);
  for(const op of operations){
   const id=`${family.id}-${variant}-${op}`;await page.setContent(html);await page.evaluate(()=>document.fonts.ready);const provenance=mutationScript(op,variant);await mutate(page,provenance);
   const afterRender=await renderSettled(page,viewport),afterInspect=afterRender.observations,afterBuf=afterRender.buffer,afterPng=afterRender.png;let changedPixels=0;
   for(let y=0;y<Math.max(beforePng.height,afterPng.height);y++)for(let x=0;x<beforePng.width;x++){
    const i=(y*beforePng.width+x)*4;let d=0;for(let c=0;c<3;c++)d+=Math.abs((beforePng.data[i+c]??255)-(afterPng.data[i+c]??255));if(d>12)changedPixels++;
   }
   const afterPath=`${id}-after.png`;await fs.writeFile(path.join(out,afterPath),afterBuf);
   const observations=establish(beforeInspect,afterInspect,{changedPixels});
   records.push({id,family:family.id,source:family.source,split:family.split,variant,provenance,before:`data/${beforePath}`,after:`data/${afterPath}`,beforeSha256:hash(beforeBuf),afterSha256:hash(afterBuf),htmlSha256:hash(html),observations,changedPixels,intent:op==='intentional_move'?'intentional':null,capture:{viewport,dpr:1,scale:'css',browser:browser.version(),locale:'en-US',timezone:'UTC',colorScheme:'light',fontsReady:true,geometryStable:true,captureAttempts:{before:beforeRender.attempts,after:afterRender.attempts},fixedContent:true,pageDimensions:{before:{width:beforePng.width,height:beforePng.height},after:{width:afterPng.width,height:afterPng.height}},masks:[]}});
  }
  await context.close();
 }
 console.log(`Rendered ${family.id}: ${records.length} pairs`);
 await fs.writeFile(`artifacts/${pilot?'pilot-':' '}data-manifest.jsonl`.replace('/ ','/'),records.map(x=>JSON.stringify(x)).join('\n')+'\n');
}
await browser.close();
const summary={pairs:records.length,seconds:(performance.now()-start)/1000,pngBytes:(await Promise.all((await fs.readdir(out)).filter(x=>x.endsWith('.png')).map(async p=>(await fs.stat(path.join(out,p))).size))).reduce((a,b)=>a+b,0),bySplit:Object.fromEntries(['train','dev','calibration','test'].map(s=>[s,records.filter(x=>x.split===s).length])),observations:Object.fromEntries(['clipping','overlap_or_occlusion','out_of_container','element_disappearance','layout_displacement'].map((l,j)=>[l,{positive:records.flatMap(r=>r.observations).filter(o=>o.labels[j]===true).length,known:records.flatMap(r=>r.observations).filter(o=>o.labels[j]!==null).length}]))};
await fs.writeFile(`artifacts/${pilot?'pilot-':''}generation.json`,JSON.stringify(summary,null,2));console.log(JSON.stringify(summary));
