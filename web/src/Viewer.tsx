import { useEffect, useRef, useState } from 'react';
import type { Candidate } from '../../core/index';
import type { Run } from './types';
type ViewMode = 'split' | 'overlay' | 'difference';
export function Viewer({run, selected, onSelect}: {run: Run; selected?: Candidate; onSelect:(id:string)=>void}) {
  const [mode,setMode]=useState<ViewMode>('split'); const [zoom,setZoom]=useState(0.5); const [opacity,setOpacity]=useState(0.5); const [boxes,setBoxes]=useState(true);
  const before=useRef<HTMLDivElement>(null), after=useRef<HTMLDivElement>(null), diff=useRef<HTMLCanvasElement>(null), frame=useRef<HTMLDivElement>(null);
  const syncing=useRef(false); const drag=useRef<{x:number;y:number;left:number;top:number;element:HTMLDivElement}|null>(null);
  function fit() {const available=frame.current?.clientWidth || 900; setZoom(Math.min(1,(available/(mode==='split'?2:1)-48)/run.analysis.width));}
  useEffect(()=>{fit();},[run.id,mode]);
  useEffect(()=>{if(!selected)return; const b=selected.box; for(const el of [before.current,after.current]) if(el) {el.scrollLeft=Math.max(0,(b.x+b.width/2)*zoom-el.clientWidth/2);el.scrollTop=Math.max(0,(b.y+b.height/2)*zoom-el.clientHeight/2);} },[selected?.id,run.id,zoom,mode]);
  useEffect(()=>{
    if(mode!=='difference'||!diff.current)return; let active=true;
    const images=[run.images?.before||run.beforeUrl,run.images?.after||run.afterUrl].map(src=>new Promise<HTMLImageElement>((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=reject;i.src=src;}));
    Promise.all(images).then(([a,b])=>{
      if(!active||!diff.current)return;
      const width=run.analysis.width,height=run.analysis.height; const canvas=diff.current; canvas.width=width;canvas.height=height;
      const c=canvas.getContext('2d')!; const off=document.createElement('canvas');off.width=width;off.height=height;const ctx=off.getContext('2d',{willReadFrequently:true})!;
      ctx.fillStyle='white';ctx.fillRect(0,0,width,height);ctx.drawImage(a,0,0);const one=ctx.getImageData(0,0,width,height);
      ctx.fillStyle='white';ctx.fillRect(0,0,width,height);ctx.drawImage(b,0,0);const two=ctx.getImageData(0,0,width,height);const out=c.createImageData(width,height);
      for(let i=0;i<out.data.length;i+=4) { const delta=Math.max(Math.abs(one.data[i]-two.data[i]),Math.abs(one.data[i+1]-two.data[i+1]),Math.abs(one.data[i+2]-two.data[i+2])); const faint=(one.data[i]+one.data[i+1]+one.data[i+2])/3;out.data[i]=delta?Math.min(255,130+delta):Math.round(faint*.18+214);out.data[i+1]=delta?Math.max(35,170-delta):Math.round(faint*.18+214);out.data[i+2]=delta?73:Math.round(faint*.18+214);out.data[i+3]=255; }
      c.putImageData(out,0,0);
    }).catch(()=>{});return()=>{active=false;};
  },[run.id,mode]);
  function sync(source:HTMLDivElement,target:HTMLDivElement|null) {if(syncing.current||!target)return;syncing.current=true;target.scrollTop=source.scrollTop;target.scrollLeft=source.scrollLeft;requestAnimationFrame(()=>{syncing.current=false;});}
  function pan(e:React.PointerEvent<HTMLDivElement>){if((e.target as HTMLElement).closest('button'))return;drag.current={x:e.clientX,y:e.clientY,left:e.currentTarget.scrollLeft,top:e.currentTarget.scrollTop,element:e.currentTarget};e.currentTarget.setPointerCapture(e.pointerId);}
  const move=(e:React.PointerEvent<HTMLDivElement>)=>{if(!drag.current)return;const d=drag.current;d.element.scrollLeft=d.left-(e.clientX-d.x);d.element.scrollTop=d.top-(e.clientY-d.y);};
  const regions=()=> <>{boxes&&run.analysis.candidates.map((c,i)=><button aria-label={`Locate region ${i+1}`} title={`Region ${i+1}: ${c.box.x}, ${c.box.y} · ${c.box.width} × ${c.box.height} pixels`} key={c.id} className={`region-box ${selected?.id===c.id?'selected':''}`} onClick={()=>onSelect(c.id)} style={{left:c.box.x*zoom,top:c.box.y*zoom,width:Math.max(6,c.box.width*zoom),height:Math.max(6,c.box.height*zoom)}}><span>{i+1}</span></button>)}{run.masks.map((m,i)=><div title={`Excluded: ${m.source}`} key={i} className="mask-region" style={{left:m.x*zoom,top:m.y*zoom,width:m.width*zoom,height:m.height*zoom}}><span>Excluded</span></div>)}</>;
  const stageStyle={width:run.analysis.width*zoom,height:run.analysis.height*zoom};
  const imgStyle={width:run.analysis.width*zoom};
  return <section className="viewer" ref={frame} aria-label="Screenshot comparison">
    <div className="viewer-toolbar"><div className="segmented" aria-label="Comparison mode">{(['split','overlay','difference'] as ViewMode[]).map(m=><button className={mode===m?'active':''} key={m} onClick={()=>setMode(m)}>{m==='split'?'Side by side':m==='overlay'?'Overlay':'Difference'}</button>)}</div><div className="zoom-controls"><button onClick={()=>setZoom(z=>Math.max(.1,z-.1))} aria-label="Zoom out">−</button><output>{Math.round(zoom*100)}%</output><button onClick={()=>setZoom(z=>Math.min(3,z+.1))} aria-label="Zoom in">+</button><button onClick={fit}>Fit</button><button className={boxes?'toggled':''} onClick={()=>setBoxes(!boxes)} aria-label="Toggle candidate boxes">▣</button></div></div>
    {mode==='overlay'&&<div className="overlay-controls"><span>Baseline</span><input aria-label="Overlay opacity" type="range" min="0" max="1" step="0.05" value={opacity} onChange={e=>setOpacity(+e.target.value)}/><span>Current</span></div>}
    <div className={`comparison ${mode}`}>
      <div className="image-pane"><div className="pane-label"><span className="status-dot"/>{mode==='split'?'BASELINE':mode==='overlay'?'BASELINE + CURRENT':'RAW PIXEL DIFFERENCE'}<span className="pane-dimension">{run.analysis.width} px wide</span></div><div className="image-scroll" ref={before} onScroll={e=>sync(e.currentTarget,after.current)} onPointerDown={pan} onPointerMove={move} onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}}><div className="image-stage" style={stageStyle}>{mode==='difference'?<canvas ref={diff} style={stageStyle} aria-label="Raw pixel difference image"/>:<><img draggable={false} alt="Baseline screenshot" src={run.images?.before||run.beforeUrl} style={imgStyle}/>{mode==='overlay'&&<img draggable={false} alt="Current overlay screenshot" className="overlay-image" src={run.images?.after||run.afterUrl} style={{...imgStyle,opacity}}/>}</>}{regions()}</div></div></div>
      {mode==='split'&&<div className="image-pane"><div className="pane-label"><span className="status-dot current"/>CURRENT<span className="pane-dimension">{run.analysis.heightDelta!==0?`${run.analysis.heightDelta>0?'+':''}${run.analysis.heightDelta} px height change`:'Same page dimensions'}</span></div><div className="image-scroll" ref={after} onScroll={e=>sync(e.currentTarget,before.current)} onPointerDown={pan} onPointerMove={move} onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}}><div className="image-stage" style={stageStyle}><img draggable={false} alt="Current screenshot" src={run.images?.after||run.afterUrl} style={imgStyle}/>{regions()}</div></div></div>}
    </div><div className="viewer-footnote"><span>↔ Synchronized position · Drag to pan</span><span>{selected?`Original pixels: ${selected.box.x}, ${selected.box.y} · ${selected.box.width} × ${selected.box.height}`:'Original screenshot coordinates'}</span></div>
  </section>;
}
