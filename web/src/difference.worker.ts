import { decodePNG } from '../../core/png';
import { differenceRaster, type Mask } from '../../core/index';
self.onmessage = async (event: MessageEvent<{before: string; after: string; masks: Mask[]}>) => {
  try {
    const read = async (url: string) => { const response = await fetch(url); if (!response.ok) throw new Error(`Screenshot could not be read (${response.status}).`); return decodePNG(new Uint8Array(await response.arrayBuffer())); };
    const before = await read(event.data.before), after = await read(event.data.after);
    const result = differenceRaster(before, after, event.data.masks);
    self.postMessage({type:'result', width:result.width, height:result.height, data:result.data}, {transfer:[result.data.buffer]});
  } catch(error) { self.postMessage({type:'error', error:error instanceof Error ? error.message : String(error)}); }
};
