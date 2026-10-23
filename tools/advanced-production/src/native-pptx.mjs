import pptxgen from 'pptxgenjs';
import JSZip from 'jszip';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {parseMermaidStructure} from './mermaid-structure.mjs';
const require=createRequire(import.meta.url);
function assertStyleOptions(options){
 if(!options||typeof options!=='object'||Array.isArray(options))throw new Error('Style options must be an object');
 const key=['x','y','w','h'].find(key=>key in options);
 if(key)throw new Error(`Geometry options are forbidden: ${key}; use the validated box/placements`);
}
export function assertBox(p,b,name='object'){
 if(!b||!['x','y','w','h'].every(k=>Number.isFinite(b[k]))||b.w<=0||b.h<=0||b.x<0||b.y<0||b.x+b.w>p.width+1e-6||b.y+b.h>p.height+1e-6)throw new Error(`Out-of-canvas or invalid geometry: ${name}`);
}
export function validateProto(p){
 if(p?.schemaVersion!==1||!['KEDI','KIRD','custom'].includes(p.family)||!p.id)throw new Error('Explicit proto schema/family/id required');
 if(!Number.isFinite(p.width)||!Number.isFinite(p.height)||p.width<=0||p.height<=0)throw new Error('Measured inch dimensions required');
 if(!p.font?.face||!Number.isFinite(p.font.bodyPt)||!Number.isFinite(p.font.titlePt))throw new Error('Measured font family/sizes required');
 for(const k of ['background','ink','accent','frame'])if(!/^[0-9A-Fa-f]{6}$/.test(p.colors?.[k]??''))throw new Error(`Six-digit color required: ${k}`);
 for(const k of ['header','content','narration'])assertBox(p,p.regions?.[k],k);
 if(!p.diagnosticOnly&&(!p.reference?.path||!/^[a-f0-9]{64}$/.test(p.reference.sha256??'')))throw new Error('Production proto requires original reference path and SHA256');
 return p;
}
export function createNativeDeck(proto){
 validateProto(proto);
 const pptx=new pptxgen();pptx.defineLayout({name:proto.id,width:proto.width,height:proto.height});pptx.layout=proto.id;
 pptx.author='ppt1 internal production tools';pptx.title=proto.id;pptx.lang='ko-KR';pptx.subject=proto.diagnosticOnly?'INTERNAL DIAGNOSTIC ONLY — VIRTUAL PROTO':'Storyboard production';
 pptx.theme={headFontFace:proto.font.face,bodyFontFace:proto.font.face,lang:'ko-KR'};
 const receipt={protoId:proto.id,diagnosticOnly:!!proto.diagnosticOnly,reference:proto.reference??null,width:proto.width,height:proto.height,nativeObjects:[],svgFallbacks:[]};
 function text(s,value,b,o={}){assertBox(proto,b,'text');assertStyleOptions(o);s.addText(String(value),{...b,fontFace:proto.font.face,fontSize:proto.font.bodyPt,color:proto.colors.ink,margin:0,...o});receipt.nativeObjects.push({type:'text',text:String(value),...b});}
 function shape(s,type,b,o={}){assertBox(proto,b,'shape');assertStyleOptions(o);s.addShape(type,{...b,fill:{color:proto.colors.background},line:{color:proto.colors.frame,width:1},...o});receipt.nativeObjects.push({type:'shape',shape:type,...b});}
 function addScene({title,narration,sceneId,speaker,cues=[],source={}}){
  if(!title||!narration||!sceneId||!speaker)throw new Error('Scene title/narration/sceneId/speaker required');
  if(!Array.isArray(cues)||cues.length===0||cues.some((cue,index)=>cue?.id!==index+1))throw new Error('Page-local cue IDs must be nonempty, start at 1 and be consecutive');
  const markers=[...narration.matchAll(/#(\d+)/g)].map(m=>Number(m[1]));
  if(markers[0]!==1)throw new Error('Narration must include a first page-local #1 cue marker');
  if(markers.some(id=>!cues.some(c=>c.id===id)))throw new Error('Narration cue marker has no page-local cue mapping');
  const s=pptx.addSlide();s.background={color:proto.colors.background};
  shape(s,pptx.ShapeType.rect,proto.regions.header,{fill:{color:proto.colors.frame},line:{color:proto.colors.frame}});
  text(s,title,proto.regions.header,{fontSize:proto.font.titlePt,color:'FFFFFF',margin:0.08});
  for(const k of ['content','narration'])shape(s,pptx.ShapeType.rect,proto.regions[k]);
  text(s,`${speaker}: ${narration}`,proto.regions.narration,{margin:0.08});
  s.addNotes(JSON.stringify({sceneId,speaker,cues,source,protoId:proto.id,diagnosticOnly:!!proto.diagnosticOnly}));return s;
 }
 function addTable(s,rows,b,o={}){assertBox(proto,b,'table');assertStyleOptions(o);s.addTable(rows,{...b,fontFace:proto.font.face,fontSize:proto.font.bodyPt,color:proto.colors.ink,border:{type:'solid',pt:1,color:proto.colors.frame},fill:proto.colors.background,margin:0.05,autoPage:false,...o});receipt.nativeObjects.push({type:'table',rows:rows.length,...b});}
 function addChart(s,data,b,o={}){assertBox(proto,b,'chart');assertStyleOptions(o);s.addChart(pptx.ChartType.bar,data,{...b,showLegend:false,showTitle:false,showValue:true,catAxisLabelFontFace:proto.font.face,valAxisLabelFontFace:proto.font.face,catAxisLabelFontSize:12,valAxisLabelFontSize:10,chartColors:[proto.colors.accent],...o});receipt.nativeObjects.push({type:'chart',series:data.length,...b});}
 function addSvg(s,svg,b){assertBox(proto,b,'svg');if(!svg.startsWith('<svg')||/<script|<foreignObject|(?:href|src)\s*=\s*["'](?:https?:|file:)/i.test(svg))throw new Error('Self-contained safe SVG required');s.addImage({data:'image/svg+xml;base64,'+Buffer.from(svg).toString('base64'),...b});receipt.nativeObjects.push({type:'svg-image',editableGeometry:false,...b});}
 async function addMermaidNative(s,source,placements,options={}){
  assertStyleOptions(options.text??{});
  const g=await parseMermaidStructure(source);
  for(const n of g.nodes){assertBox(proto,placements?.[n.id],n.id);if(!['rect','square','round','diamond'].includes(n.shape))throw new Error(`Native shape semantics unsupported: ${n.shape}`);}
  for(const e of g.edges)if(e.label)assertBox(proto,options.edgeLabels?.[e.id],`edge label ${e.id}`);
  for(const e of g.edges){
   if(!['arrow_point','arrow_open'].includes(e.type))throw new Error(`Native edge semantics unsupported: ${e.type}`);
   const a=placements[e.from],b=placements[e.to];if(!a||!b)throw new Error('Missing endpoint placement');
   const horiz=['LR','RL'].includes(g.direction),reverse=['RL','BT'].includes(g.direction);
   const x1=horiz?(reverse?a.x:a.x+a.w):a.x+a.w/2,y1=horiz?a.y+a.h/2:(reverse?a.y:a.y+a.h);
   const x2=horiz?(reverse?b.x+b.w:b.x):b.x+b.w/2,y2=horiz?b.y+b.h/2:(reverse?b.y+b.h:b.y);
   s.addShape(pptx.ShapeType.line,{x:Math.min(x1,x2),y:Math.min(y1,y2),w:Math.abs(x2-x1)||0.001,h:Math.abs(y2-y1)||0.001,flipH:x2<x1,flipV:y2<y1,line:{color:proto.colors.accent,width:1.5,...(e.type==='arrow_point'?{endArrowType:'triangle'}:{})}});
   receipt.nativeObjects.push({type:'connector',from:e.from,to:e.to});
   if(e.label){if(!options.edgeLabels?.[e.id])throw new Error('Labeled edges need explicit edgeLabels geometry');text(s,e.label,options.edgeLabels[e.id]);}
  }
  for(const n of g.nodes){const b=placements[n.id];shape(s,n.shape==='diamond'?pptx.ShapeType.diamond:n.shape==='round'?pptx.ShapeType.roundRect:pptx.ShapeType.rect,b,{line:{color:proto.colors.accent,width:1.5}});text(s,n.label,b,{align:'center',valign:'mid',...options.text});}return g;
 }
 async function save(outputPath){
  const zip=await JSZip.loadAsync(await pptx.write({outputType:'nodebuffer'}));
  // PptxGenJS 4.0.1 Node writes a broken SVG PNG fallback. Replace only that
  // generated preview. Original SVG and all editable slide objects stay intact.
  const svgs=Object.keys(zip.files).filter(n=>/^ppt\/media\/.*\.svg$/.test(n));
  if(svgs.length){
   let sharp=require('sharp'),rendererSource='project-local';
   const installedVersion=sharp.versions.sharp;
   const modules=process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES;
   if(modules&&process.env.PPT1_SHARP_FORCE_LOCAL!=='1'){
    try{const sharedSharp=require(path.join(modules,'sharp'));if(sharedSharp.versions.sharp===installedVersion){sharp=sharedSharp;rendererSource='shared-exact-version';}}catch{/* Local exact dependency remains available. */}
   }
   for(const name of svgs){const m=name.match(/^(.*-)(\d+)\.svg$/);if(!m)throw new Error('Unexpected pinned SVG media naming');const png=m[1]+(Number(m[2])-1)+'.png';if(!zip.file(png))throw new Error('SVG preview pairing missing');zip.file(png,await sharp(await zip.file(name).async('nodebuffer')).png().toBuffer());receipt.svgFallbacks.push({svg:name,png,renderer:'sharp',rendererVersion:installedVersion,rendererSource,sourcePreserved:true});}
  }
  await fs.mkdir(path.dirname(outputPath),{recursive:true});await fs.writeFile(outputPath,await zip.generateAsync({type:'nodebuffer',compression:'DEFLATE'}));return receipt;
 }
 return {pptx,proto,receipt,addScene,text,shape,addTable,addChart,addSvg,addMermaidNative,save};
}
