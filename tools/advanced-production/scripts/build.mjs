import fs from 'node:fs/promises';
import {createNativeDeck} from '../src/native-pptx.mjs';
const [input,output]=process.argv.slice(2);
if(!input||!output)throw new Error('Usage: npm run build -- job.json new-output.pptx');
// Fail closed on output replacement and on absent/unverified original reference.
try{await fs.access(output);throw new Error('Output already exists; choose a new versioned name');}catch(e){if(e.code!=='ENOENT')throw e;}
const job=JSON.parse(await fs.readFile(input,'utf8'));
if(!job.proto.diagnosticOnly){
 const {createHash}=await import('node:crypto');
 const sha=createHash('sha256').update(await fs.readFile(job.proto.reference.path)).digest('hex');
 if(sha!==job.proto.reference.sha256)throw new Error('Original proto reference SHA256 mismatch');
}
const deck=createNativeDeck(job.proto);
for(const scene of job.scenes){
 const slide=deck.addScene(scene);
 for(const op of scene.objects??[]){
  if(op.type==='text')deck.text(slide,op.text,op.box,op.options);
  else if(op.type==='shape')deck.shape(slide,op.shape,op.box,op.options);
  else if(op.type==='table')deck.addTable(slide,op.rows,op.box,op.options);
  else if(op.type==='chart')deck.addChart(slide,op.data,op.box,op.options);
  else if(op.type==='svg')deck.addSvg(slide,op.svg,op.box);
  else if(op.type==='mermaid')await deck.addMermaidNative(slide,op.source,op.placements,op.options);
  else throw new Error(`Unsupported native object type: ${op.type}`);
 }
}
const receipt=await deck.save(output);await fs.writeFile(output+'.receipt.json',JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify({output,proto:job.proto.id,diagnosticOnly:!!job.proto.diagnosticOnly}));
