export type Tag = {id:string; title:string};
export type Task = {id:string; title:string; notes:string|null; status:'open'|'completed'|'canceled'|'trashed'; when:string|null; whenKind?:string|null; listIds?:string[]; deadline:string|null; createdAt?:string|null; modifiedAt?:string|null; projectId:string|null; areaId:string|null; tags:Tag[]|null; revision:string; availableFields:string[]|Record<string,boolean>};
export type Container = {id:string; title:string; areaId?:string|null;status?:'open'|'completed'|'canceled'|'trashed'};
export type TaskDraft={title:string;notes:string;tags:string[];when:string;deadline:string;location:string};
export function taskWhen(task:Task){if(task.when)return task.when;if(task.listIds?.includes('today'))return 'today';if(task.whenKind==='someday'||task.listIds?.includes('someday'))return 'someday';if(task.whenKind==='anytime'||task.listIds?.includes('anytime')||task.listIds?.includes('inbox'))return 'anytime';return '';}
export function draftFromTask(task:Task):TaskDraft{return {title:task.title,notes:task.notes??'',tags:(task.tags??[]).map(tag=>tag.title),when:taskWhen(task),deadline:task.deadline??'',location:task.projectId?`project:${task.projectId}`:task.areaId?`area:${task.areaId}`:''};}
export function projectIsOpen(project:Container){return project.status==='open';}
export function quickDefaults(view:string){return {when:view==='today'?'today':view==='someday'?'someday':view==='upcoming'?'tomorrow':view.startsWith('project:')?'':'anytime',location:view.startsWith('project:')||view.startsWith('area:')?view:''};}
export function quickEntryArguments(draft:TaskDraft){const args:Record<string,unknown>={title:draft.title.trim(),notes:draft.notes};const project=draft.location.startsWith('project:');if(draft.when&&!(project&&['anytime','someday'].includes(draft.when))&&(draft.when!=='anytime'||draft.location))args.when=draft.when;if(draft.tags.length)args.tags=draft.tags;if(draft.deadline)args.deadline=draft.deadline;if(project)args.projectId=draft.location.slice(8);if(draft.location.startsWith('area:'))args.areaId=draft.location.slice(5);return args;}
export type Snapshot = {view?:string;tasks:Task[]; projects:Container[]; areas:Container[]; tags:Tag[]; lists:unknown; total:number; offset:number; limit:number; nextOffset:number|null; hasMore:boolean; capabilities:Record<string,unknown>};
export type Envelope = {ok:boolean; data?:Record<string,any>; error?:{code:string;message:string;details?:Record<string,any>}; operation?:{id:string;status:string}; meta?:{demo?:boolean;adapter?:string;settings?:Record<string,any>}};
export function fieldAvailable(task:Task, field:string){return Array.isArray(task.availableFields)?task.availableFields.includes(field):task.availableFields?.[field]===true;}
export function envelope(input:any):Envelope {
  if(input?.structuredContent) return input.structuredContent as Envelope;
  if(typeof input?.ok==='boolean') return input;
  for(const item of input?.content??[])if(item.type==='text'){try {const value=JSON.parse(item.text);if(typeof value?.ok==='boolean')return value;}catch{}}
  return {ok:false,error:{code:'INVALID_RESULT',message:'Things returned a result this workspace could not read.'}};
}
export function snapshotData(value:Envelope):Snapshot|null {
  const data=value.data;
  if(!value.ok || !Array.isArray(data?.tasks))return null;
  return {...data, tasks:data.tasks, projects:data.projects??[],areas:data.areas??[],tags:data.tags??[], total:data.total??data.tasks.length,offset:data.offset??0,limit:data.limit??20,nextOffset:data.nextOffset??(data.hasMore&&data.tasks.length?(data.offset??0)+data.tasks.length:null),hasMore:!!data.hasMore,capabilities:data.capabilities??{}} as Snapshot;
}
export class ThingsError extends Error {
  constructor(public response:Envelope){super(response.error?.message??'The action could not be completed.');this.name='ThingsError';}
  get code(){return this.response.error?.code;}
  get uncertain(){return this.response.operation?.status==='uncertain' || this.code==='UNCERTAIN';}
}
export function changedArguments(before:Task,draft:TaskDraft){
  const args:Record<string,unknown>={id:before.id};
  if(before.title!==draft.title.trim())args.title=draft.title.trim();
  if(fieldAvailable(before,'notes')&&(before.notes??'')!==draft.notes)args.notes=draft.notes;
  const tagTitles=(before.tags??[]).map(t=>t.title);
  if(fieldAvailable(before,'tags')&&JSON.stringify(tagTitles)!==JSON.stringify(draft.tags))args.tags=draft.tags;
  const currentWhen=taskWhen(before);
  if(fieldAvailable(before,'when')&&draft.when&&draft.when!==currentWhen)args.when=draft.when;
  if(fieldAvailable(before,'deadline')&&(before.deadline??'')!==draft.deadline)args.deadline=draft.deadline||null;
  const currentLocation=before.projectId?`project:${before.projectId}`:before.areaId?`area:${before.areaId}`:'';
  if(currentLocation!==draft.location){
    if(draft.location.startsWith('project:'))args.projectId=draft.location.slice(8);
    else if(draft.location.startsWith('area:'))args.areaId=draft.location.slice(5);
    else{args.projectId=null;args.areaId=null;}
  }
  return args;
}
