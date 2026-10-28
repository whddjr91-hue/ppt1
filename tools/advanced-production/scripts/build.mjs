import fs from 'node:fs/promises';
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
 const python=process.env.PROTOTYPE_POLICY_PYTHON||process.env.CODEX_PRIMARY_RUNTIME_PYTHON||(process.platform==='win32'?'python':'python3');
 const gate=fileURLToPath(new URL('./verify-production.py',import.meta.url));
 const checked=spawnSync(python,[gate,'--job',input],{encoding:'utf8',shell:false});
 if(checked.error||checked.status!==0)throw new Error('Prototype policy blocked production: '+(checked.stdout||checked.stderr||checked.error));
 const verified=JSON.parse(checked.stdout);
 if(job.templateReuse){
  // Native source pages, layouts and shared resources stay intact; no generic chrome.
  const os=await import('node:os');
  const tmp=await fs.mkdtemp(path.join(os.tmpdir(),'ppt1-reuse-'));
  try{
   const reuseJob=path.join(tmp,'reuse.json');
   await fs.writeFile(reuseJob,JSON.stringify({reference:{path:verified.reference_path,sha256:verified.prototype_sha256},pages:job.templateReuse.pages}));
   const result=spawnSync(python,[fileURLToPath(new URL('./reuse-prototype.py',import.meta.url)),'--job',reuseJob,'--output',path.resolve(output)],{encoding:'utf8',shell:false});
   if(result.error||result.status!==0)throw new Error('Native reuse failed: '+(result.stdout||result.stderr||result.error));
   const populated=spawnSync(python,[gate,'--job',input,'--receipt',path.resolve(output)+'.receipt.json'],{encoding:'utf8',shell:false});
   if(populated.error||populated.status!==0)throw new Error('Native draft rejected; not accepted: '+(populated.stdout||populated.stderr||populated.error));
   console.log(result.stdout.trim());
  }finally{await fs.rm(tmp,{recursive:true,force:true});}
  process.exit(0);
 }
}
const {createNativeDeck}=await import('../src/native-pptx.mjs');
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
