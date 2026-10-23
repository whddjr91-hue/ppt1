// S2-GEOM-001 regression: negative inputs only. Never creates a PPTX.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {createNativeDeck} from '../src/native-pptx.mjs';
const base=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const output=path.resolve(base,'../../.local/advanced-tests/session3');
await fs.mkdir(output,{recursive:true});
const proto=JSON.parse(await fs.readFile(path.join(base,'fixtures/kird-virtual-proto.json'),'utf8'));
const deck=createNativeDeck(proto),box={x:1,y:1,w:2,h:1};
const forbidden=[{x:-1},{y:-1},{w:999},{h:999},{x:NaN},{y:Infinity},{w:undefined},Object.create({x:-1})];
const calls={text:o=>deck.text({},'test',box,o),shape:o=>deck.shape({},deck.pptx.ShapeType.rect,box,o),table:o=>deck.addTable({},[['test']],box,o),chart:o=>deck.addChart({},[{name:'test',labels:['A'],values:[1]}],box,o)};
const tests=[];
for(const [type,call] of Object.entries(calls))for(let index=0;index<forbidden.length;index++){
 assert.throws(()=>call(forbidden[index]),/Geometry options are forbidden/);tests.push({surface:type,case:index,rejected:true});
}
for(let index=0;index<forbidden.length;index++){
 await assert.rejects(()=>deck.addMermaidNative({},'flowchart LR\n A --> B',{A:box,B:{x:4,y:1,w:2,h:1}},{text:forbidden[index]}),/Geometry options are forbidden/);
 tests.push({surface:'mermaid.options.text',case:index,rejected:true});
}
assert.equal(deck.receipt.nativeObjects.length,0,'Rejection must precede object mutation');
const cliOps=[{type:'text',text:'test'},{type:'shape',shape:'rect'},{type:'table',rows:[['test']]},{type:'chart',data:[{name:'test',labels:['A'],values:[1]}]}];
for(const op of cliOps){
 const job=path.join(output,`geometry-negative-${op.type}.json`),target=path.join(output,`geometry-negative-${op.type}.pptx`);
 const payload={proto,scenes:[{title:'negative-only',narration:'#1 guard',sceneId:'NEGATIVE',speaker:'test',cues:[{id:1,trigger:'guard'}],objects:[{...op,box,options:{x:-1}}]}]};
 await fs.writeFile(job,JSON.stringify(payload));
 const run=spawnSync(process.execPath,[path.join(base,'scripts/build.mjs'),job,target],{encoding:'utf8'});
 assert.notEqual(run.status,0);assert.match(run.stderr,/Geometry options are forbidden/);
 await assert.rejects(()=>fs.access(target));tests.push({surface:'CLI op.options '+op.type,rejected:true,outputCreated:false});
}
const mermaidJob=path.join(output,'geometry-negative-mermaid.json'),mermaidTarget=path.join(output,'geometry-negative-mermaid.pptx');
await fs.writeFile(mermaidJob,JSON.stringify({proto,scenes:[{title:'negative-only',narration:'#1 guard',sceneId:'NEGATIVE',speaker:'test',cues:[{id:1,trigger:'guard'}],objects:[{type:'mermaid',source:'flowchart LR\n A --> B',placements:{A:box,B:{x:4,y:1,w:2,h:1}},options:{text:{w:999}}}]}]}));
const mermaidRun=spawnSync(process.execPath,[path.join(base,'scripts/build.mjs'),mermaidJob,mermaidTarget],{encoding:'utf8'});
assert.notEqual(mermaidRun.status,0);assert.match(mermaidRun.stderr,/Geometry options are forbidden/);await assert.rejects(()=>fs.access(mermaidTarget));tests.push({surface:'CLI mermaid.options.text',rejected:true,outputCreated:false});
const hash=async file=>createHash('sha256').update(await fs.readFile(file)).digest('hex');
const cueDeck=createNativeDeck(proto),scene={title:'cue guard',narration:'#1 original text',sceneId:'CUE',speaker:'test',cues:[{id:1,trigger:'original'}]};
const cueCases=[{...scene,cues:[]},{...scene,cues:[],narration:'no marker'},{...scene,narration:'no marker'},{...scene,cues:[{id:2}]},{...scene,cues:[{id:1},{id:2}],narration:'#2 out of order #1'}];
for(let index=0;index<cueCases.length;index++){assert.throws(()=>cueDeck.addScene(cueCases[index]),/Page-local cue IDs|first page-local #1/);tests.push({surface:'addScene page-local cue contract',case:index,rejected:true});}
assert.equal(cueDeck.receipt.nativeObjects.length,0,'Invalid cues must precede object mutation');
cueDeck.addScene(scene);cueDeck.addScene({...scene,sceneId:'CUE2'});assert.equal(cueDeck.pptx._slides.length,2);
const result={issue:'S2-GEOM-001',passed:true,negativeCases:tests.length,tests,pageCueFirstMarkerRequired:true,pageCueResetRepeatedAcrossTwoInMemoryScenesAllowed:true,approvedNarrationRewritten:false,nativeAdapterSha256:await hash(path.join(base,'src/native-pptx.mjs')),existingDiagnosticArtifacts:[...await fs.readdir(output)].filter(n=>/^(?:kird|kedi).*(?:\.pptx|\.pdf|\.png)$/.test(n)),pptxCreated:false,fullDiagnosticsRerun:false};
await fs.writeFile(path.join(output,'geometry-guard-regression.json'),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({issue:result.issue,passed:true,negativeCases:tests.length,nativeAdapterSha256:result.nativeAdapterSha256}));
