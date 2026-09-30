import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import {chromium} from '@playwright/test';
import {build} from 'esbuild';
const html=await readFile('dist/things-workspace.html','utf8');
assert.ok(!/<script[^>]+src=/.test(html),'selfcontained script');
assert.ok(!/<link[^>]+href=/.test(html),'selfcontained stylesheet');
const modelBuild=await build({entryPoints:['src/types.ts'],bundle:true,write:false,format:'esm',platform:'node'});
const model=await import(`data:text/javascript;base64,${Buffer.from(modelBuild.outputFiles[0].text).toString('base64')}`);
const task={id:'test',title:'Original',notes:'Keep this',tags:[{id:'t',title:'Work'}],when:null,whenKind:'someday',deadline:'2026-10-02',areaId:'area-1',projectId:null,revision:'one',availableFields:['notes','tags','when','deadline','projectId','areaId']};
assert.deepEqual(model.changedArguments(task,{title:'Original',notes:'Keep this',tags:['Work'],when:'someday',deadline:'2026-10-02',location:'area:area-1'}),{id:'test'});
assert.deepEqual(model.changedArguments(task,{title:'New',notes:'Keep this',tags:['Work'],when:'someday',deadline:'',location:'project:proj-1'}),{id:'test',title:'New',deadline:null,projectId:'proj-1'});
// Native Today placement can exist with a null raw activation date. A title edit must preserve it.
const todayTask={...task,when:null,whenKind:'scheduled',listIds:['today'],projectId:'proj-old',areaId:'effective-area'};
assert.deepEqual(model.changedArguments(todayTask,{...model.draftFromTask(todayTask),title:'Only title changed'}),{id:'test',title:'Only title changed'});
assert.deepEqual(model.changedArguments(todayTask,{...model.draftFromTask(todayTask),location:'project:proj-new'}),{id:'test',projectId:'proj-new'});
assert.deepEqual(model.changedArguments(todayTask,{...model.draftFromTask(todayTask),location:'area:area-new'}),{id:'test',areaId:'area-new'});
assert.deepEqual(model.changedArguments(todayTask,{...model.draftFromTask(todayTask),location:''}),{id:'test',projectId:null,areaId:null});
assert.equal(model.taskWhen({...todayTask,when:'2026-10-03'}),'2026-10-03','Native placement does not invent or replace a raw date');
const quick={title:' Quick task ',notes:'',tags:[],when:'anytime',deadline:'',location:''};
assert.deepEqual(model.quickEntryArguments(quick),{title:'Quick task',notes:''},'Default unparented quick entry stays in Inbox');
assert.deepEqual(model.quickEntryArguments({...quick,location:'project:proj-1'}),{title:'Quick task',notes:'',projectId:'proj-1'});
assert.equal(model.snapshotData({ok:true,data:{task}}),null);
assert.equal(model.envelope({content:[{type:'text',text:JSON.stringify({ok:false,error:{code:'CONFLICT',message:'Changed'}})}]}).error.code,'CONFLICT');
if(process.env.THINGSCTL_TEST_STATIC_ONLY==='1'){console.log('UI static tests passed: selfcontained bundle, field preservation, native Today membership, parent moves, Inbox Quick Entry, result envelopes.');process.exit(0);}
const server=createServer((req,res)=>{res.writeHead(200,{'content-type':'text/html;charset=utf-8'});res.end(html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const url=`http://127.0.0.1:${server.address().port}/?demo=1`;
const browser=await chromium.launch({executablePath:process.env.THINGSCTL_CHROME_PATH??'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
const errors=[];const page=await browser.newPage({viewport:{width:1024,height:780}});page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(url);await page.getByRole('heading',{name:'Today',exact:true}).waitFor();await page.getByRole('checkbox',{name:'Complete Review the autumn launch brief'}).waitFor();
 assert.equal(await page.getByRole('listitem').count(),3);
 await page.getByRole('button',{name:'Search loaded tasks',exact:true}).click();await page.getByRole('searchbox').fill('lake');assert.equal(await page.getByRole('listitem').count(),1);await page.getByRole('button',{name:'Close search'}).click();
 await page.getByRole('button',{name:/Review the autumn launch brief/}).last().click();await page.getByRole('textbox',{name:'Task title',exact:true}).fill('A clear launch brief');await page.getByLabel('Tags, separated by commas').fill('Work, Focus');await page.getByRole('button',{name:'Save',exact:true}).click();await page.getByRole('button',{name:/A clear launch brief/}).last().waitFor();
 await page.getByRole('checkbox',{name:'Complete A clear launch brief'}).click();await page.waitForFunction(()=>document.querySelectorAll('[role="listitem"]').length===2);
 await page.getByRole('button',{name:'Logbook',exact:false}).click();await page.getByRole('checkbox',{name:'Reopen A clear launch brief'}).waitFor();
 await page.getByRole('button',{name:'Inbox',exact:false}).first().click();await page.getByRole('button',{name:'New task',exact:true}).click();await page.getByRole('textbox',{name:'New task title'}).fill('A fictional integration test');await page.getByRole('button',{name:'Add To-Do',exact:true}).click();await page.getByRole('checkbox',{name:'Complete A fictional integration test'}).waitFor();
 await page.getByRole('button',{name:/A fictional integration test/}).last().click();await page.getByRole('button',{name:'Attach task to conversation'}).click();await page.getByRole('status').filter({hasText:'Demo attachment selected'}).waitFor();
 await page.getByRole('button',{name:'Move task to Trash'}).click();await page.getByRole('button',{name:'Move to Trash',exact:true}).click();await page.getByRole('button',{name:'Trash',exact:false}).first().click();await page.getByRole('button',{name:/A fictional integration test/}).last().waitFor();
 await page.getByRole('button',{name:'Today',exact:false}).first().click();
 await mkdir('../work/ui-qa',{recursive:true});
 for(const width of [320,560,768,1024]){
  await page.setViewportSize({width,height:780});await page.evaluate(()=>document.documentElement.dataset.theme='light');await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`No overflow at ${width}px`);
  await page.screenshot({path:`../work/ui-qa/light-${width}.png`,fullPage:true});
  await page.evaluate(()=>document.documentElement.dataset.theme='dark');await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));await page.screenshot({path:`../work/ui-qa/dark-${width}.png`,fullPage:true});
  await page.getByRole('button',{name:/Polish the small details/}).last().click();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`Editor no overflow at ${width}px`);
  await page.screenshot({path:`../work/ui-qa/editor-${width}.png`,fullPage:true});await page.getByRole('button',{name:'Close',exact:true}).click();
 }
 await page.setViewportSize({width:320,height:780});await page.getByRole('button',{name:'Open navigation'}).click();await page.getByRole('button',{name:'Upcoming',exact:true}).click();await page.getByRole('heading',{name:'Upcoming'}).waitFor();await page.getByRole('button',{name:'New task',exact:true}).click();assert.equal(await page.getByRole('dialog').isVisible(),true);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.keyboard.press('Escape');assert.equal(await page.getByRole('dialog').count(),0);
 // Explicit fictional transport tests exercise conflict and uncertain saves without touching Things.
 const testPage=await browser.newPage({viewport:{width:760,height:760}});testPage.on('pageerror',e=>errors.push(e.message));
 await testPage.addInitScript(()=>{
  const task={id:'fixture-1',title:'Fixture task',notes:'Original notes',status:'open',when:null,whenKind:'anytime',deadline:null,projectId:null,areaId:null,tags:[],revision:'r1',availableFields:['title','notes','tags','when','deadline','projectId','areaId']};
  globalThis.__testCalls=[];globalThis.__testMode='conflict';
  globalThis.__THINGSCTL_TEST_TRANSPORT__=async(name,args)=>{
   globalThis.__testCalls.push({name,args});
   if(name==='thingsctl_workspace_snapshot')return {ok:true,data:{tasks:[task],projects:[],areas:[],tags:[],total:1,offset:0,limit:100,hasMore:false,capabilities:{}}};
   if(name==='thingsctl_get')return {ok:true,data:{task:{...task,title:'Edited in Things',revision:'r2'}}};
   if(name==='thingsctl_workspace_mutate'){
    if(globalThis.__testMode==='conflict')return {ok:false,error:{code:'CONFLICT',message:'This task changed in Things.',details:{task:{...task,title:'Edited in Things',revision:'r2'}}},operation:{id:args.operationId,status:'failed'}};
    return {ok:false,error:{code:'UNCERTAIN',message:'Change not confirmed.'},operation:{id:args.operationId,status:'uncertain'}};
   }
  };
 });
 await testPage.goto(url);await testPage.getByRole('button',{name:'Fixture task',exact:true}).click();await testPage.getByRole('textbox',{name:'Task title',exact:true}).fill('My draft');await testPage.getByRole('button',{name:'Save',exact:true}).click();await testPage.getByText('Latest in Things',{exact:true}).waitFor();assert.equal(await testPage.getByRole('textbox',{name:'Task title',exact:true}).inputValue(),'My draft');await testPage.getByRole('button',{name:'Keep my draft for review'}).click();
 await testPage.evaluate(()=>globalThis.__testMode='uncertain');await testPage.getByRole('button',{name:'Save',exact:true}).click();await testPage.getByRole('button',{name:'Check latest task'}).waitFor();const count=await testPage.evaluate(()=>globalThis.__testCalls.filter(c=>c.name==='thingsctl_workspace_mutate').length);await testPage.waitForTimeout(350);assert.equal(await testPage.evaluate(()=>globalThis.__testCalls.filter(c=>c.name==='thingsctl_workspace_mutate').length),count,'Uncertain writes never retry automatically');
 assert.equal(await testPage.getByRole('textbox',{name:'Task title',exact:true}).inputValue(),'My draft');
 assert.deepEqual(errors,[],'No browser errors');
 console.log('UI passed: model preservation, search, edit/tags, complete/logbook, add/trash, context, 320–1024 layouts, light/dark, mobile navigation/dialog, conflict drafts, uncertain writes.');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
