import json
import os
import subprocess

def test_original_long_page_and_font_settling_capture():
    script="""
import {chromium} from 'playwright';
import {families,pageHTML} from './ml/scenes.mjs';
import {renderSettled} from './ml/render.mjs';
const browser=await chromium.launch();const results=[];
try {
 for(const id of ['article','player']) {
  const page=await browser.newPage({viewport:{width:900,height:760}});
  await page.setContent(pageHTML(families.find(f=>f.id===id),0));
  const rendered=await renderSettled(page,{width:900,height:760});
  const actual=await page.evaluate(()=>document.documentElement.scrollHeight);
  results.push({id,width:rendered.png.width,pngHeight:rendered.png.height,pageHeight:actual,attempts:rendered.attempts});
  await page.close();
 }
} finally {await browser.close();}
console.log(JSON.stringify(results));
"""
    output=subprocess.run([os.environ.get('NODE','node'),'--input-type=module','-e',script],capture_output=True,text=True,check=True,timeout=45)
    cases=json.loads(output.stdout)
    assert len(cases)==2
    for case in cases:
        assert case['pngHeight']==case['pageHeight']>760
        assert case['width']==900
        assert 1<=case['attempts']<=3
