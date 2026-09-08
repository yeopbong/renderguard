
export async function inspect(page){
 return await page.evaluate(()=>{
  const rect=r=>({x:r.x,y:r.y,width:r.width,height:r.height});
  return [...document.querySelectorAll('[data-observe]')].map(e=>{
   const r=e.getBoundingClientRect(),s=getComputedStyle(e),b=document.getElementById(e.dataset.container),br=b?.getBoundingClientRect();
   const visible=s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity)>.05&&r.width>0&&r.height>0;
   const range=document.createRange();range.selectNodeContents(e); const textBoxes=[...range.getClientRects()].filter(q=>q.width>1&&q.height>1);
   const clipped=(s.overflowY==='hidden'||s.overflow==='hidden'||s.overflow==='clip')&&textBoxes.some(q=>q.bottom>r.bottom+1||q.right>r.right+1||q.top<r.top-1||q.left<r.left-1);
   let covered=0,total=0;
   for(let iy=1;iy<8;iy++)for(let ix=1;ix<8;ix++){
    const x=r.x+r.width*ix/8,y=r.y+r.height*iy/8;
    if(x<0||x>=innerWidth||y<0||y>=innerHeight)continue;
    total++;const top=document.elementFromPoint(x,y);
    if(top&&top!==e&&!e.contains(top)&&!top.contains(e)){
     const ts=getComputedStyle(top),bg=ts.backgroundColor;
     if(Number(ts.opacity)>.1&&bg!=='rgba(0, 0, 0, 0)'&&bg!=='transparent')covered++;
    }
   }
   const boundaryVisible=!!br&&Number.parseFloat(getComputedStyle(b).borderWidth)>0;
   const outside=boundaryVisible&&visible&&(r.left<br.left-2||r.right>br.right+2||r.top<br.top-2||r.bottom>br.bottom+2);
   return {id:e.id,box:rect(r),container:br?rect(br):null,visible,clipped,coverage:total?covered/total:null,outside,boundaryVisible,textBoxes:textBoxes.map(rect)};
  });
 });
}
export function establish(before,after,pixelEvidence){
 const observations=[];
 for(const a of after){
  const b=before.find(x=>x.id===a.id);if(!b)continue;
  const union={x:Math.min(a.box.x,b.box.x),y:Math.min(a.box.y,b.box.y),width:Math.max(a.box.x+a.box.width,b.box.x+b.box.width)-Math.min(a.box.x,b.box.x),height:Math.max(a.box.y+a.box.height,b.box.y+b.box.height)-Math.min(a.box.y,b.box.y)};
  const moved=Math.hypot(a.box.x-b.box.x,a.box.y-b.box.y)>3;
  const labels=[a.clipped&&!b.clipped,a.coverage===null||b.coverage===null?null:a.coverage>b.coverage+.06,a.boundaryVisible?a.outside&&!b.outside:null,!a.visible&&b.visible,moved&&a.visible&&b.visible];

  if(pixelEvidence.changedPixels===0)for(let j=0;j<labels.length;j++)if(labels[j]===true)labels[j]=null;
  observations.push({element:a.id,box:union,labels,evidence:{before:b,after:a,changedPixels:pixelEvidence.changedPixels}});
 }
 return observations;
}
