import {build} from 'esbuild';
import {mkdir,writeFile,readFile,stat} from 'node:fs/promises';
import {dirname,resolve,join} from 'node:path';
const result=await build({entryPoints:['src/main.tsx'],bundle:true,minify:true,write:false,format:'iife',target:['es2022'],legalComments:'external',outfile:'workspace.js',jsx:'automatic',metafile:true});
const js=result.outputFiles.find(f=>f.path.endsWith('.js')).text.replace(/<\/script/gi,'<\\/script');
const css=result.outputFiles.find(f=>f.path.endsWith('.css'))?.text??'';
const html=`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><title>ThingsCTL</title><style>${css}</style></head><body><div id="root"></div><script>${js}</script></body></html>`;
await mkdir('dist',{recursive:true});await writeFile('dist/things-workspace.html',html);
for(const file of result.outputFiles.filter(f=>f.path.endsWith('.LEGAL.txt')))await writeFile(`dist/${file.path.split('/').at(-1)}`,file.text);
const packages=new Map();
for(const input of Object.keys(result.metafile.inputs)){
 if(!input.includes('node_modules/'))continue;
 let directory=dirname(resolve(input));
 while(directory!==dirname(directory)){
  try{const packageJson=JSON.parse(await readFile(join(directory,'package.json'),'utf8'));if(packageJson.name){packages.set(packageJson.name,{directory,packageJson});break;}}catch{}
  directory=dirname(directory);
 }
}
let notices='ThingsCTL workspace dependency licenses\nOriginal application code; no RemCTL source is included.\n';
for(const [name,{directory,packageJson}] of [...packages.entries()].sort()){
 let license='';for(const filename of ['LICENSE','LICENSE.txt','LICENSE.md','license','license.txt','COPYING']){try{license=await readFile(join(directory,filename),'utf8');break;}catch{}}
 if(!license)throw new Error(`Missing bundled dependency license: ${name}`);
 notices+=`\n\n----- ${name} ${packageJson.version} (${packageJson.license??'See license'}) -----\n${license}`;
}
await writeFile('THIRD-PARTY-NOTICES.txt',notices);await writeFile('dist/THIRD-PARTY-NOTICES.txt',notices);
console.log(`Bundled workspace: ${Math.round(Buffer.byteLength(html)/1024)} KB`);
