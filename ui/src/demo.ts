import type {Envelope,Task,Snapshot} from './types';
const today=new Date().toLocaleDateString('en-CA');
const tomorrow=new Date(Date.now()+86400000).toLocaleDateString('en-CA');
const fields=['id','title','notes','status','when','whenKind','deadline','createdAt','modifiedAt','projectId','areaId','tags'];
let tasks:Task[]=[
 {id:'demo-brief',title:'Review the autumn launch brief',notes:'A little clarity before the week gets busy.\nRead the draft and collect the last few questions.',status:'open',when:today,whenKind:'scheduled',deadline:tomorrow,projectId:'demo-launch',areaId:'demo-work',tags:[{id:'tag-work',title:'Work'}],listIds:['today'],revision:'demo-1',availableFields:fields},
 {id:'demo-design',title:'Polish the small details',notes:'Check spacing, type, and the flow from one task to the next.',status:'open',when:today,whenKind:'scheduled',deadline:null,projectId:'demo-site',areaId:'demo-work',tags:[{id:'tag-focus',title:'Focus'}],listIds:['today'],revision:'demo-2',availableFields:fields},
 {id:'demo-walk',title:'Take a walk by the lake',notes:'',status:'open',when:today,whenKind:'scheduled',deadline:null,projectId:null,areaId:'demo-personal',tags:[],listIds:['today'],revision:'demo-3',availableFields:fields},
 {id:'demo-research',title:'Gather a few ideas for the weekend',notes:'Somewhere with good coffee and no rush.',status:'open',when:null,whenKind:'anytime',deadline:null,projectId:'demo-weekend',areaId:'demo-personal',tags:[],revision:'demo-4',availableFields:fields},
 {id:'demo-inbox',title:'An idea worth coming back to',notes:'',status:'open',when:null,whenKind:'anytime',deadline:null,projectId:null,areaId:null,tags:[],revision:'demo-5',availableFields:fields},
 {id:'demo-upcoming',title:'Share the first look',notes:'',status:'open',when:tomorrow,whenKind:'scheduled',deadline:null,projectId:'demo-launch',areaId:'demo-work',tags:[{id:'tag-work',title:'Work'}],revision:'demo-6',availableFields:fields},
 {id:'demo-someday',title:'Learn to make a really good sourdough',notes:'',status:'open',when:null,whenKind:'someday',deadline:null,projectId:null,areaId:'demo-personal',tags:[],revision:'demo-7',availableFields:fields},
 {id:'demo-done',title:'Set the direction for ThingsCTL',notes:'',status:'completed',when:null,whenKind:'anytime',deadline:null,projectId:'demo-site',areaId:'demo-work',tags:[],revision:'demo-8',availableFields:fields},
];
const projects:import('./types').Container[]=[{id:'demo-launch',title:'Autumn launch',areaId:'demo-work',status:'open'},{id:'demo-site',title:'Website refresh',areaId:'demo-work',status:'open'},{id:'demo-weekend',title:'Weekend away',areaId:'demo-personal',status:'open'}];
const areas=[{id:'demo-work',title:'Work'},{id:'demo-personal',title:'Personal'}];
const tags=[{id:'tag-work',title:'Work'},{id:'tag-focus',title:'Focus'}];
let counter=10;
function result(data:Record<string,any>,operationId?:string):Envelope{return {ok:true,data,meta:{demo:true,adapter:'fictional fixture'},...(operationId?{operation:{id:operationId,status:'verified'}}:{})};}
function matches(t:Task,view:string){if(view.startsWith('project:'))return t.projectId===view.slice(8)&&t.status==='open';if(view.startsWith('area:'))return t.areaId===view.slice(5)&&t.status==='open';if(view==='logbook')return ['completed','canceled'].includes(t.status);if(view==='trash')return t.status==='trashed';if(t.status!=='open')return false;if(view==='today')return t.listIds?.includes('today')||t.when===today;if(view==='upcoming')return !!t.when&&t.when>today;if(view==='inbox')return !t.projectId&&!t.areaId;if(view==='someday')return t.whenKind==='someday';return t.whenKind!=='someday';}
export async function demoCall(name:string,args:Record<string,any>):Promise<Envelope>{
 await new Promise(r=>setTimeout(r,90));
 if(name==='thingsctl_doctor')return result({installed:true,connected:true,adapter:'Demo fixtures',version:'Demo',capabilities:{checklists:false,headings:false,evening:false,reminder:false},message:'Fictional data. No tasks in Things are read or changed.'});
 if(name==='thingsctl_get'){const task=tasks.find(t=>t.id===args.id);return task?result({task}):{ok:false,error:{code:'NOT_FOUND',message:'Task not found.'}};}
 if(name==='thingsctl_workspace_snapshot'){
  const view=args.view??'today';const selected=tasks.filter(t=>matches(t,view));const offset=args.offset??0;const limit=args.limit??20;const hasMore=offset+limit<selected.length;
  return result({tasks:selected.slice(offset,offset+limit),projects,areas,tags,lists:[],total:selected.length,offset,limit,nextOffset:hasMore?offset+limit:null,hasMore,capabilities:{checklists:false,headings:false,evening:false,reminder:false}} satisfies Snapshot);
 }
 if(name==='thingsctl_workspace_mutate'){
  const {command,arguments:a={},expectedRevision,operationId}=args;
  if(command==='add'){const task:Task={id:`demo-${++counter}`,title:a.title,notes:a.notes??'',tags:(a.tags??[]).map((title:string)=>({id:title,title})),status:'open',when:['today','tomorrow'].includes(a.when)?(a.when==='today'?today:tomorrow):/^\d{4}-\d{2}-\d{2}$/.test(a.when)?a.when:null,whenKind:a.when==='someday'?'someday':a.when&&!['anytime','someday'].includes(a.when)?'scheduled':'anytime',deadline:a.deadline??null,areaId:a.areaId??null,projectId:a.projectId??null,revision:`demo-${counter}`,availableFields:fields};tasks=[...tasks,task];return result({task},operationId);}
  const index=tasks.findIndex(t=>t.id===a.id);if(index<0)return {ok:false,error:{code:'NOT_FOUND',message:'Task not found.'}};
  if(expectedRevision&&expectedRevision!==tasks[index].revision)return {ok:false,error:{code:'CONFLICT',message:'This task changed in Things.',details:{task:tasks[index],actualRevision:tasks[index].revision}},operation:{id:operationId,status:'failed'}};
  if(command==='show')return result({task:tasks[index]});
  const task={...tasks[index]};
  if(command==='complete')task.status='completed';else if(command==='reopen')task.status='open';else if(command==='trash')task.status='trashed';else if(command==='update'){
   Object.assign(task,a);if('tags'in a)task.tags=a.tags.map((title:string)=>({id:title,title}));
   if('when'in a){task.when=['today','tomorrow'].includes(a.when)?(a.when==='today'?today:tomorrow):/^\d{4}-\d{2}-\d{2}$/.test(a.when)?a.when:null;task.whenKind=a.when==='someday'?'someday':task.when?'scheduled':'anytime';task.listIds=a.when==='today'?['today']:a.when==='someday'?['someday']:task.when?['upcoming']:['anytime'];}
  }
  task.revision=`demo-${++counter}`;tasks[index]=task;return result({task},operationId);
 }
 return {ok:false,error:{code:'UNSUPPORTED',message:'This demo does not support that action.'}};
}
