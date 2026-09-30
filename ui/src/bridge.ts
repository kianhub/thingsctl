import {App,applyDocumentTheme,applyHostStyleVariables} from '@modelcontextprotocol/ext-apps';
import {OpenAIExtensions} from '@openai/mcp-extensions/app';
import {Envelope,Task,ThingsError,envelope,snapshotData} from './types';
import {demoCall} from './demo';
export const demo=new URLSearchParams(location.search).get('demo')==='1';
export const app=new App({name:'ThingsCTL',version:'0.1.1'},{},{autoResize:true});
export const extensions=new OpenAIExtensions(app);
type Event={type:'result';value:Envelope}|{type:'connection';connected:boolean;message?:string}|{type:'context';context:any};
const listeners=new Set<(event:Event)=>void>();let latest:Event|undefined;let initialSnapshot=false;
function emit(event:Event){if(event.type==='result')latest=event;for(const listener of listeners)listener(event);}
export function subscribe(listener:(event:Event)=>void){listeners.add(listener);if(latest)listener(latest);return()=>{listeners.delete(listener);};}
function contextChanged(context:any){if(context?.theme&&!['light','dark'].includes(document.documentElement.dataset.appearanceChoice??''))applyDocumentTheme(context.theme);if(context?.styles?.variables)applyHostStyleVariables(context.styles.variables);document.documentElement.style.setProperty('--host-safe-bottom',`${Math.max(0,context?.safeAreaInsets?.bottom??0)}px`);emit({type:'context',context});}
app.ontoolresult=(result)=>{const value=envelope(result);if(snapshotData(value))initialSnapshot=true;emit({type:'result',value});};
app.onhostcontextchanged=contextChanged;
let ready:Promise<void>|undefined;
export function connect(){
 if(ready)return ready;
 ready=demo?Promise.resolve().then(()=>emit({type:'connection',connected:true})):app.connect().then(async()=>{
  contextChanged(app.getHostContext());emit({type:'connection',connected:true});
  const host=app.getHostContext();if(host?.displayMode==='inline'&&host?.availableDisplayModes?.includes('fullscreen')){
   // A host may decline the preferred layout while the MCP connection remains usable.
   await app.requestDisplayMode({mode:'fullscreen'}).catch(()=>{});
  }
 }).catch(error=>{emit({type:'connection',connected:false,message:'Open ThingsCTL from the installed plugin to connect to Things.'});throw error;});
 return ready;
}
export function hasInitialSnapshot(){return initialSnapshot;}
export async function call(name:string,args:Record<string,any>={}):Promise<Envelope>{
 await connect();
 const testTransport=(globalThis as any).__THINGSCTL_TEST_TRANSPORT__;
 const raw=demo&&typeof testTransport==='function'?await testTransport(name,args):demo?await demoCall(name,args):await app.callServerTool({name,arguments:args});
 const structured=(raw as any).structuredContent;
 const value=!demo&&name.startsWith('thingsctl_settings_')&&structured&&structured.ok===undefined?{ok:true,data:structured}:envelope(raw);
 if(!value.ok)throw new ThingsError(value);
 return value;
}
export async function mutate(command:string,args:Record<string,any>,revision?:string):Promise<Envelope>{
 if(args.when==='tomorrow'){const date=new Date();date.setDate(date.getDate()+1);args={...args,when:`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`};}
 // Keep the ID after a transport failure or uncertain write; the user must explicitly inspect before retrying.
 const key=`thingsctl-operation:${JSON.stringify([command,args,revision])}`;
 let operationId:string=crypto.randomUUID();try{operationId=sessionStorage.getItem(key)??operationId;sessionStorage.setItem(key,operationId);}catch{}
 try{
  const response=await call('thingsctl_workspace_mutate',{command,arguments:args,operationId,...(revision?{expectedRevision:revision}:{})});
  if(response.operation?.status!=='verified'&&command!=='show')throw new ThingsError({ok:false,error:{code:'UNCERTAIN',message:'Things has not confirmed this change. Check the latest task before trying again.'},operation:{id:operationId,status:'uncertain'}});
  try{sessionStorage.removeItem(key);}catch{}return response;
 }catch(error){if(error instanceof ThingsError&&!error.uncertain){try{sessionStorage.removeItem(key);}catch{}}throw error;}
}
export function attachmentAvailable(){return demo||!!extensions.modelContext;}
export async function attach(tasks:Task[]){
 if(demo)return;
 if(!extensions.modelContext)throw new Error('Selected task attachments are unavailable in this host.');
 await extensions.modelContext.update({content:tasks.map(task=>({type:'text' as const,text:`Things task: ${task.title}\nID: ${task.id}\nStatus: ${task.status}${task.notes?`\nNotes: ${task.notes}`:''}${task.when?`\nWhen: ${task.when}`:''}${task.deadline?`\nDeadline: ${task.deadline}`:''}`,_meta:{'openai/title':task.title,'thingsctl/id':task.id}})),structuredContent:{tasks:tasks.map(({id,title,status,revision})=>({id,title,status,revision}))}});
}
