import {readFile,readdir,mkdir,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
const root = process.cwd();
const names = new Set(['react','react-dom','scheduler','fast-png','iobuffer','pako','onnxruntime-common','onnxruntime-web']);
const out = join(root,'web/public/licenses'); await mkdir(out,{recursive:true});
const entries=[];
for(const directory of await readdir(join(root,'node_modules/.pnpm'))){
 const base=join(root,'node_modules/.pnpm',directory,'node_modules');
 let children;try{children=await readdir(base);}catch{continue;}
 for(const name of children){
  if(!names.has(name)||entries.some(e=>e.name===name))continue;
  const dir=join(base,name);const metadata=JSON.parse(await readFile(join(dir,'package.json'),'utf8'));
  const files=(await readdir(dir)).filter(n=>/^licen[cs]e(\.|$)/i.test(n));
  if(!files.length)continue;
  const content=(await Promise.all(files.map(file=>readFile(join(dir,file),'utf8')))).join('\n\n');
  await writeFile(join(out,`${name}.txt`),content);entries.push({name,version:metadata.version,license:metadata.license,file:`${name}.txt`});
 }
}
await writeFile(join(out,'index.json'),JSON.stringify(entries,null,2)+'\n');
console.log(`Preserved license texts for ${entries.length} bundled dependencies.`);
