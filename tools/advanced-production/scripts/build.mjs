import fs from 'node:fs/promises';
import {createNativeDeck} from '../src/native-pptx.mjs';
const [input,output]=process.argv.slice(2);
if(!input||!output)throw new Error('Usage: npm run build -- job.json new-output.pptx');
// Fail closed on output replacement and on absent/unverified original reference.
try{await fs.access(output);throw new Error('Output already exists; choose a new versioned name');}catch(e){if(e.code!=='ENOENT')throw e;}
const job=JSON.parse(await fs.readFile(input,'utf8'));
if(!job.proto.diagnosticOnly){
 const {spawnSync}=await import('node:child_process');
 const {fileURLToPath}=await import('node:url');
 const path=await import('node:path');
 if(!job.prototypePolicy?.binding||!job.prototypePolicy?.scenes)throw new Error('Production requires prototypePolicy.binding and scenes; read storyboard-prototype');
 const base=path.dirname(path.resolve(input));
 const binding=path.resolve(base,job.prototypePolicy.binding),scenePlan=path.resolve(base,job.prototypePolicy.scenes);
 const script=fileURLToPath(new URL('../../../.claude/skills/storyboard-prototype/scripts/prototype_guard.py',import.meta.url));
 const python=process.env.PROTOTYPE_POLICY_PYTHON||process.env.CODEX_PRIMARY_RUNTIME_PYTHON||(process.platform==='win32'?'python':'python3');
 const checked=spawnSync(python,[script,'preflight','--binding',binding,'--scenes',scenePlan],{encoding:'utf8',shell:false});
 if(checked.error||checked.status!==0)throw new Error('Prototype policy blocked production: '+(checked.stdout||checked.stderr||checked.error));
 const guard=JSON.parse(checked.stdout),b=JSON.parse(await fs.readFile(binding,'utf8')),plan=JSON.parse(await fs.readFile(scenePlan,'utf8'));
 const scenes=Array.isArray(plan)?plan:plan.scenes;
 if(guard.prototype_sha256!==job.proto.reference?.sha256)throw new Error('Build reference is not the selected storyboard prototype');
 if(job.proto.font?.face!==b.observed_profile.screen_font)throw new Error('Build screen font differs from measured prototype');
 if(job.scenes.length!==scenes.length)throw new Error('Build and reviewed scene plan counts differ');
 const norm=s=>s.replace(/#[0-9０-９]+/g,'').replace(/\s+/g,'');
 for(let i=0;i<scenes.length;i++)if(!scenes[i].scene_id||job.scenes[i].sceneId!==scenes[i].scene_id||norm(job.scenes[i].narration)!==norm(scenes[i].narration))throw new Error('Build scene identity/narration differs from prototype-bound plan');
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
