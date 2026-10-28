// Negative integration cases: never generates a presentation.
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const dir=await fs.mkdtemp(path.join(os.tmpdir(),'ppt1-gate-'));
try{
 const build=fileURLToPath(new URL('./build.mjs',import.meta.url));
 const input=path.join(dir,'job.json'),output=path.join(dir,'never.pptx'),execution=path.join(dir,'execution.json');
 const cases=[
  {execution:null,expected:/requires prototypePolicy.execution/},
  {execution:{kind:'full',phase:'bulkk'},expected:/explicit pilot or bulk/},
  {execution:{kind:'full',phase:'bulk'},expected:/Reviewed representative pages required/}
 ];
 for(const c of cases){
  await fs.writeFile(input,JSON.stringify({proto:{diagnosticOnly:false},scenes:[],prototypePolicy:{binding:'unused.json',scenes:'unused.json',...(c.execution?{execution:'execution.json'}:{})}}));
  if(c.execution)await fs.writeFile(execution,JSON.stringify(c.execution));
  const r=spawnSync(process.execPath,[build,input,output],{encoding:'utf8',shell:false});
  assert.notEqual(r.status,0);assert.match(r.stderr+r.stdout,c.expected);
  await assert.rejects(()=>fs.access(output));
 }
 console.log(JSON.stringify({passed:true,negativeCases:cases.length,pptxCreated:false}));
}finally{await fs.rm(dir,{recursive:true,force:true});}
