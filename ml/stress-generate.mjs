
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {chromium} from 'playwright';
import {PNG} from 'pngjs';
import {families,pageHTML,operations,mutate,mutationScript} from './scenes.mjs';
import {establish} from './verify.mjs';
import {renderSettled} from './render.mjs';
import {writeTensors} from '../capture/tensors.ts';
const out='data/stress';await fs.mkdir(out,{recursive:true});const browser=await chromium.launch({headless:true});const records=[];const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const domainText={ja:['表示の変更を確認','保存した証拠を比較してください','この項目は確認後に更新できます','概要と詳細情報','予定と設定'],zh:['检查页面显示变化','请比较原始证据并保存审核结果','此项目可以在确认后更新','概览和详细信息','计划与设置']};
for(const family of families.filter(f=>f.split==='test'))for(const language of ['ja','zh']){
 const variant=language==='ja'?4:5;const viewport={width:900,height:760};const context=await browser.newContext({viewport,locale:language,timezoneId:'UTC',deviceScaleFactor:1});const page=await context.newPage();const html=pageHTML(family,variant);
 async function set(){await page.setContent(html);await page.evaluate(({phrases,language})=>{document.documentElement.lang=language;const walker=document.createTreeWalker(document.querySelector('main'),NodeFilter.SHOW_TEXT);let node,i=0;while(node=walker.nextNode()){if(node.textContent.trim())node.textContent=phrases[i++%phrases.length];}}, {phrases:domainText[language],language});await page.evaluate(()=>document.fonts.ready);}
 await set();const renderedBefore=await renderSettled(page,viewport),bi=renderedBefore.observations,before=renderedBefore.buffer;const beforePath=`${out}/${family.id}-${language}-before.png`;await fs.writeFile(beforePath,before);const bp=renderedBefore.png;
 for(const operation of operations){await set();await mutate(page,mutationScript(operation,variant));const renderedAfter=await renderSettled(page,viewport),ai=renderedAfter.observations,after=renderedAfter.buffer;const id=`${family.id}-${language}-${operation}`,afterPath=`${out}/${id}-after.png`;await fs.writeFile(afterPath,after);const ap=PNG.sync.read(after);let changedPixels=0;for(let i=0;i<Math.max(bp.data.length,ap.data.length);i+=4){let d=0;for(let c=0;c<3;c++)d+=Math.abs((bp.data[i+c]??255)-(ap.data[i+c]??255));if(d>12)changedPixels++;}
 const observations=establish(bi,ai,{changedPixels});await writeTensors({before:beforePath,after:afterPath,output:`${out}/${id}`});records.push({id,family:family.id,split:'test',language,before:beforePath,after:afterPath,beforeSha256:hash(before),afterSha256:hash(after),observations,changedPixels,tensors:`${out}/${id}`});}
 await context.close();console.log(family.id,language);
}
await browser.close();await fs.writeFile('artifacts/stress-manifest.jsonl',records.map(r=>JSON.stringify(r)).join('\n')+'\n');
