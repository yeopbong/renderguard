import fs from 'node:fs/promises';
import {decodePNG} from '../core/png.ts';
import {analyzePair,tensorsForCandidate} from '../core/index.ts';
const samples=JSON.parse(await fs.readFile('web/public/examples/index.json','utf8'));const results=[];
for(const sample of samples){
 const [a,b]=await Promise.all(['before','after'].map(side=>fs.readFile(`web/public/examples/${sample[side]}`)));const trials=[];
 for(let trial=0;trial<6;trial++){
  const t0=performance.now(),before=decodePNG(a),after=decodePNG(b),t1=performance.now(),analysis=analyzePair(before,after),t2=performance.now();for(const c of analysis.candidates)tensorsForCandidate(before,after,c);const t3=performance.now();trials.push({decodeMilliseconds:t1-t0,candidateMilliseconds:t2-t1,tensorMilliseconds:t3-t2,totalMilliseconds:t3-t0,candidates:analysis.candidates.length,width:before.width,beforeHeight:before.height,afterHeight:after.height});
 }
 results.push({id:sample.id,cold:trials[0],warm:trials.slice(1)});
}
await fs.writeFile('artifacts/preprocessing-timing.json',JSON.stringify({runtime:process.version,platform:process.platform,arch:process.arch,processRssBytes:process.memoryUsage().rss,definition:'No cached pixels, candidates or tensors. First trial cold; five additional warm trials in one process. Runtime import cost excluded and measured in the end-to-end command.',results},null,2));
