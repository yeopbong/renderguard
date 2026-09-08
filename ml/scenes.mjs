import {targetHTML,targetCSS} from './targets.mjs';

export const families = [
 ['ledger','A transaction ledger with summary footer'],['profile','A profile with two-column biography'],['schedule','A time-slot timetable'],['kanban','A three-lane work board'],['invoice','A printable invoice with totals'],['mail','A split mailbox'],['catalog','A product catalog grid'],['settings','A stacked settings form'],['article','A long editorial article'],['checkout','A checkout with order rail'],['gallery','An asymmetric gallery'],['metrics','A metric dashboard'],['forum','A threaded discussion'],['timeline','A vertical project timeline'],['nav','A navigation menu and article'],['modal','A dialog above a muted page'],['pricing','A pricing comparison'],['directory','A contact directory'],['player','A media player with playlist'],['calendar','A month calendar'],['search','A faceted search layout'],['wizard','A multistep form'],['code','A code review split pane'],['map','A schematic map and legend']
].map(([id,structure],i)=>({id,structure,split:i<14?'train':i<18?'dev':i<21?'calibration':'test',source:`original-${id}`,dependencies:['base-css-v2']}));
export const operations = ['repeat','content','color','clip','cover','overflow','hide','move','intentional_move','compound','transparent_overlap','ineffective'];
const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;');
export function pageHTML(family,variant){
 const mobile=variant%3===2; const dark=variant%2===1; const word=variant===4?'表示を確認してください':variant===5?'请检查此控件的内容':'Review the complete details';
 const widget=targetHTML(family,variant);
 const card=(t)=>`<section><h3>${t}</h3><p>Review the latest details and continue when ready.</p><div class="bars"><i></i><i></i><i></i></div></section>`;
 const nav=`<nav>Overview &nbsp; Activity &nbsp; Settings &nbsp; Help</nav>`;
 const list=Array.from({length:6},(_,i)=>`<p class="row">${i+1}. Reference item <strong>${32+i*7}</strong></p>`).join('');
 let body;
 switch(family.id){
 case 'ledger':body=`<table><thead><tr><th>Date</th><th>Account</th><th>Total</th></tr></thead><tbody>${Array.from({length:5},(_,i)=>`<tr><td>Sep ${i+1}</td><td>General ledger</td><td>${i*72+34}</td></tr>`).join('')}</tbody></table>${widget}`;break;
 case 'profile':body=`<div class="columns"><aside><div class="portrait"></div><h2>Jordan Lee</h2><p>Editor and designer</p></aside><article>${card('Biography')}${widget}</article></div>`;break;
 case 'schedule':body=`<div class="schedule"><aside>09:00<br><br>10:00<br><br>11:00</aside><article>${card('Morning planning')}${widget}</article></div>`;break;
 case 'kanban':body=`<div class="three"><div><h2>Backlog</h2>${card('Research')}</div><div><h2>In progress</h2>${widget}</div><div><h2>Complete</h2>${card('Archive')}</div></div>`;break;
 case 'invoice':body=`<header><h2>Invoice 0142</h2><p>Sep 08 · Reference 2026</p></header>${list}<footer>${widget}</footer>`;break;
 case 'mail':body=`<div class="mail"><aside>${list}</aside><article><h2>Project update</h2><p>Here are this week’s review notes.</p>${widget}${card('Attachments')}</article></div>`;break;
 case 'catalog':body=`<div class="three">${card('Desk lamp')}${card('Field notebook')}${widget}${card('Travel mug')}${card('Desk organizer')}${card('Poster print')}</div>`;break;
 case 'settings':body=`<form><label>Display name<input value="Jordan"></label><label>Language<select><option>English</option></select></label>${widget}<label>Email<input value="demo@example.invalid"></label></form>`;break;
 case 'article':body=`<article class="reading"><h2>A guide to careful observation</h2>${('<p>Changes deserve context. Compare both versions and inspect the evidence before reaching a decision.</p>').repeat(8)}${widget}${('<p>The original evidence is preserved for a later review.</p>').repeat(10)}</article>`;break;
 case 'checkout':body=`<div class="checkout"><form><h2>Shipping details</h2><input value="Sample address"><input value="City"><input value="Postal code">${widget}</form><aside>${card('Order summary')}${list}</aside></div>`;break;
 case 'gallery':body=`<div class="gallery">${card('Mountain study')}<div>${widget}${card('Sea study')}</div>${card('Urban study')}</div>`;break;
 case 'metrics':body=`<div class="three">${card('Visits')}${card('Orders')}${card('Returns')}</div><div class="columns"><article>${widget}</article><aside>${list}</aside></div>`;break;
 case 'forum':body=`<h2>Discussion: page review</h2>${card('Opening post')}<div class="thread">${card('First reply')}<div class="thread">${widget}</div></div>`;break;
 case 'timeline':body=`<div class="timeline">${card('January: discovery')}${card('April: prototype')}${widget}${card('September: release')}</div>`;break;
 case 'nav':body=`<div class="mail"><aside><h3>Documentation</h3>${nav}${list}</aside><article>${widget}${card('Getting started')}</article></div>`;break;
 case 'modal':body=`<div class="backdrop">${card('Workspace')}<div class="dialog"><h2>Review your changes</h2>${widget}<button>Continue</button></div></div>`;break;
 case 'pricing':body=`<div class="three">${card('Basic plan')}<div><h2>Standard plan</h2>${widget}</div>${card('Team plan')}</div><table><tr><td>Support</td><td>Included</td></tr></table>`;break;
 case 'directory':body=`<div class="directory">${Array.from({length:3},(_,i)=>card(`Team member ${i+1}`)).join('')}${widget}</div>`;break;
 case 'player':body=`<div class="player"><div class="screen">▶</div><div>${widget}</div></div><div class="playlist">${list}</div>`;break;
 case 'calendar':body=`<div class="calendar">${Array.from({length:7},(_,i)=>`<section><h3>${i+1}</h3>${i===3?widget:'Meeting<br>10:30'}</section>`).join('')}</div>`;break;
 case 'search':body=`<input value="Find reference items"><div class="search"><aside>${card('Filters')}</aside><div>${card('First result')}${widget}${card('Third result')}</div></div>`;break;
 case 'wizard':body=`<div class="steps"><b>1 Account</b><b>2 Details</b><b>3 Review</b></div><form class="reading"><h2>Confirm details</h2>${widget}<label>Notes<textarea>Ready for review</textarea></label><button>Continue</button></form>`;break;
 case 'code':body=`<div class="code"><pre>function review() {\n  preserveEvidence();\n  return status;\n}\n\n// Before version</pre><article>${widget}<pre>review();\nexport default status;</pre></article></div>`;break;
 default:body=`<div class="map"><div class="roads"></div>${widget}</div><div class="three">${card('North')}${card('Central')}${card('South')}</div>`;
 }
 return `<!doctype html><html lang="en"><meta charset="utf-8"><style>*{box-sizing:border-box}html{background:${dark?'#152335':'#edf1f4'};color:${dark?'#ecf3fa':'#1f344b'};font:15px Arial,sans-serif}body{margin:0;padding:20px}main{max-width:1120px;margin:auto}h1{font-size:24px}h2{font-size:19px}h3{font-size:15px;margin:0 0 12px}section,aside,article,form,table{min-width:0}section{background:${dark?'#253d55':'white'};border:2px solid ${dark?'#65849d':'#8195a8'};border-radius:8px;padding:14px;margin:10px 0;position:relative}p{line-height:1.6}nav,.steps{background:#2b597a;color:white;padding:16px;border-radius:6px;margin-bottom:18px}.columns,.checkout,.mail,.schedule,.search,.code,.player{display:grid;gap:22px;grid-template-columns:1fr 2fr}.checkout{grid-template-columns:2fr 1fr}.three{display:grid;gap:14px;grid-template-columns:repeat(3,minmax(0,1fr))}.gallery{display:grid;gap:18px;grid-template-columns:1fr 1.8fr 1fr}.directory{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.row{padding:9px;border-bottom:1px solid #8395a7}.row strong{float:right}.reading{max-width:620px;margin:auto}.thread{margin-left:34px;border-left:3px solid #759ab2;padding-left:18px}.timeline{max-width:650px;border-left:5px solid #5093ac;padding-left:25px}.calendar{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.calendar>section{min-height:210px}.calendar #target{font-size:12px}.backdrop{background:#63798e;padding:25px}.dialog{max-width:520px;background:${dark?'#152335':'#edf1f4'};padding:22px;margin:20px auto;box-shadow:0 5px 20px #152335}.screen{height:230px;background:#31445e;color:white;display:grid;place-items:center;font-size:70px}.steps{display:flex;justify-content:space-between}.portrait{border-radius:50%;width:110px;height:110px;background:linear-gradient(135deg,#c47a56,#648daa)}table{width:100%;border-collapse:collapse;background:${dark?'#253d55':'white'}}th,td{padding:14px;border:1px solid #97a5b2;text-align:left}input,select,textarea{display:block;width:100%;margin:10px 0 22px;padding:12px;border:1px solid #879dad;border-radius:5px;font:inherit}button{background:#236f92;color:white;padding:12px 22px;border:0;border-radius:6px}.bars i{display:block;height:12px;margin:8px 0;background:#8bb5ce}.bars i:nth-child(2){width:72%}.bars i:nth-child(3){width:43%}#boundary{overflow:visible;min-width:130px}#target{position:relative;background:${variant%2?'#286b96':'#297e75'};color:white;border:2px solid ${variant%2?'#154262':'#185c4b'};padding:12px;min-height:96px;width:100%;font-size:${variant===3?17:14}px;line-height:1.5;border-radius:4px}#target span{display:block}#cover{display:none}.map{height:390px;position:relative;background:repeating-linear-gradient(35deg,#bad0bb 0px,#bad0bb 50px,#f1e6bc 51px,#f1e6bc 60px);padding:35px}.map #boundary{max-width:360px}.code pre{padding:22px;background:#1a2938;color:#e5eaf1;white-space:pre-wrap}@media(max-width:500px){.three,.gallery,.columns,.mail,.checkout,.search,.player,.code{grid-template-columns:1fr}.calendar{grid-template-columns:repeat(2,minmax(0,1fr))}.directory{grid-template-columns:1fr}body{padding:14px}.thread{margin-left:15px}}${targetCSS}</style><main><h1>RenderGuard sample · ${esc(family.structure)}</h1>${nav}${body}<footer><p>Example data · All values are fixed</p></footer></main></html>`;
}
export function mutationScript(operation,variant){
 const severity=[.22,.36,.55,.72,.4,.6][variant];
 return {operation,severity,target:variant%2===0?'target':'peer'};
}
export async function mutate(page,provenance){
 await page.evaluate(({operation,severity,target})=>{
  const e=document.getElementById(target), c=document.querySelector('#cover'), b=document.querySelector('#boundary');
  if(operation==='content')e.firstElementChild.append(document.createTextNode(' Updated.'));
  if(operation==='color')e.style.backgroundColor='#864c93';
  if(operation==='clip'||operation==='compound'){e.style.height=`${e.getBoundingClientRect().height*(1-severity)}px`;e.style.minHeight='0';e.style.overflow='hidden';}
  if(operation==='cover'||operation==='compound'||operation==='transparent_overlap'){
   const r=e.getBoundingClientRect(),p=b.getBoundingClientRect();Object.assign(c.style,{display:'block',position:'absolute',left:`${r.x-p.x+r.width*.2}px`,top:`${r.y-p.y+r.height*.18}px`,width:`${r.width*.65}px`,height:`${r.height*.6}px`,background:operation==='transparent_overlap'?'transparent':'#d9b653',zIndex:'5',pointerEvents:operation==='transparent_overlap'?'none':'auto'});
  }
  if(operation==='overflow'){e.style.transform=`translateX(${b.clientWidth*(.22+severity*.5)}px)`;}
  if(operation==='hide'){e.style.visibility=severity>.4?'hidden':'visible';if(severity<=.4)e.style.opacity='0';}
  if(operation==='move'||operation==='intentional_move')e.style.transform=`translate(${12+severity*30}px,${5+severity*18}px)`;
  if(operation==='ineffective'){e.style.setProperty('width','100%');e.dataset.requestedChange='ineffective';}
 },provenance);
}
