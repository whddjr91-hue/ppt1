import {JSDOM} from 'jsdom';
// DOM only for Mermaid label sanitization; scripts/resources are disabled.
const dom=new JSDOM('');
globalThis.window??=dom.window;globalThis.document??=dom.window.document;
const {default:mermaid}=await import('mermaid');
mermaid.initialize({startOnLoad:false,securityLevel:'strict',flowchart:{htmlLabels:false}});
export async function parseMermaidStructure(source){
 if(typeof source!=='string'||!source.trim()||source.length>100000)throw new Error('Mermaid source required, maximum 100000 characters');
 if(/%%\{|^\s*---|\bclick\s+/m.test(source))throw new Error('Directives/frontmatter/click handlers unsupported');
 const result=await mermaid.parse(source,{suppressErrors:false});
 if(!result||!result.diagramType.startsWith('flowchart'))throw new Error('Native conversion supports flowcharts only');
 const d=await mermaid.mermaidAPI.getDiagramFromText(source);
 const nodes=[...d.db.getVertices().values()].map(v=>({id:v.id,label:v.text??v.id,shape:v.type??'rect'}));
 const edges=d.db.getEdges().map(e=>({id:e.id,from:e.start,to:e.end,label:e.text??'',type:e.type}));
 if(nodes.some(n=>/<[^>]*>/.test(n.label))||edges.some(e=>/<[^>]*>/.test(e.label)))throw new Error('Plain-text labels required');
 if(d.db.getSubGraphs().length)throw new Error('Subgraph native geometry unsupported');
 return {schemaVersion:1,engine:'mermaid@12.2.0',diagramType:result.diagramType,direction:d.db.getDirection(),nodes,edges};
}
