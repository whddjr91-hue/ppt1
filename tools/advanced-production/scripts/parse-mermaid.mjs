import fs from 'node:fs/promises';
import {parseMermaidStructure} from '../src/mermaid-structure.mjs';
const [input,output]=process.argv.slice(2);
if(!input)throw new Error('Usage: npm run mermaid -- source.mmd [graph.json]');
const graph=await parseMermaidStructure(await fs.readFile(input,'utf8'));
if(output)await fs.writeFile(output,JSON.stringify(graph,null,2)+'\n');else console.log(JSON.stringify(graph,null,2));
