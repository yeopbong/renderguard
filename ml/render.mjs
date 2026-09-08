import {PNG} from 'pngjs';
import {inspect} from './verify.mjs';
/** The capture itself can settle fallback font metrics. Retake boundedly, or fail. */
export async function renderSettled(page,viewport){
 await page.evaluate(()=>document.fonts.ready);
 for(let attempt=0;attempt<3;attempt++){
  const height=await page.evaluate(()=>Math.max(document.documentElement.scrollHeight,innerHeight));
  const buffer=await page.screenshot({fullPage:true,clip:{x:0,y:0,width:viewport.width,height},animations:'disabled',scale:'css'});
  const png=PNG.sync.read(buffer);const afterHeight=await page.evaluate(()=>Math.max(document.documentElement.scrollHeight,innerHeight));
  if(png.width===viewport.width&&png.height===height&&height===afterHeight)return {buffer,png,observations:await inspect(page),attempts:attempt+1};
 }
 throw new Error('Page geometry did not settle to the complete captured dimensions after three attempts');
}
