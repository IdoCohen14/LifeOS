import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {DailyMail} from './daily-mail';
import {RecordForm} from './record-form';
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const t=(_he:string,en:string)=>en;
it('offers calendar review without silently saving or reviewing the message',async()=>{
 const fetch=vi.fn().mockImplementation(async(url:string)=>({ok:true,status:200,json:async()=>url.endsWith('/queue')?[{id:'fixture',subject:'Important fixture',sender:'Teacher fixture',snippet:'Tomorrow perhaps',source_url:'https://mail.google.com/mail/u/0/#inbox/fixture'}]:{connected:true,last_success:1}}));vi.stubGlobal('fetch',fetch);
 const open=vi.fn();render(<DailyMail csrf="fixture" t={t} onUnauthorized={vi.fn()} onConnect={vi.fn()} onCreateTask={vi.fn()} onCreateEvent={open}/>);
 fireEvent.click(await screen.findByRole('button',{name:'Add important date to calendar'}));
 expect(open).toHaveBeenCalledWith({title:'Important fixture',notes:'Teacher fixture\nhttps://mail.google.com/mail/u/0/#inbox/fixture'});
 expect(fetch.mock.calls).toHaveLength(2);
});
it('opens an editable draft without reviewing mail or saving a task',async()=>{
 const fetch=vi.fn().mockImplementation(async(url:string)=>({ok:true,status:200,json:async()=>url.endsWith('/queue')?[{id:'fixture',subject:'Course reminder',sender:'Teacher fixture',snippet:'Do not copy this body',source_url:'https://mail.google.com/mail/u/0/#inbox/fixture'}]:{connected:true,last_success:1}}));vi.stubGlobal('fetch',fetch);
 const open=vi.fn();render(<DailyMail csrf="fixture" t={t} onUnauthorized={vi.fn()} onConnect={vi.fn()} onCreateTask={open}/>);
 fireEvent.click(await screen.findByRole('button',{name:'Create task from email'}));
 expect(open).toHaveBeenCalledWith({title:'Course reminder',notes:'Teacher fixture\nhttps://mail.google.com/mail/u/0/#inbox/fixture'});
 expect(screen.getByRole('heading',{name:'Course reminder'})).toBeInTheDocument();expect(fetch.mock.calls).toHaveLength(2);
});
it('requires explicit save and retains edited title without inferring a due date',async()=>{
 const save=vi.fn().mockResolvedValue(undefined);render(<RecordForm editor={{kind:'task',draft:{title:'Course reminder',notes:'Teacher fixture\nhttps://mail.google.com/mail/u/0/#inbox/fixture'}}} settings={{display_name:'',language:'en',theme:'dark',timezone:'Asia/Jerusalem'}} t={t} onSave={save} onClose={vi.fn()}/>);
 expect(save).not.toHaveBeenCalled();expect(screen.getByLabelText('Due date')).toHaveValue('');fireEvent.change(screen.getByLabelText('Title'),{target:{value:'Ask about timetable'}});fireEvent.click(screen.getByRole('button',{name:'Save'}));
 await waitFor(()=>expect(save).toHaveBeenCalledWith('task',expect.objectContaining({title:'Ask about timetable',due:null,notes:'Teacher fixture\nhttps://mail.google.com/mail/u/0/#inbox/fixture'}),undefined));
});
it('restores the last reviewed mail only within its connection revision and clears stale undo permanently',async()=>{
 const message={id:'undo-fixture',subject:'Undo fixture',sender:'Teacher fixture',snippet:'',source_url:'https://mail.google.com/mail/u/0/#inbox/fixture',connection_revision:1};
 let queue=[message],revision=1;
 const actions:unknown[]=[];
 const fetch=vi.fn().mockImplementation(async(url:string,init?:RequestInit)=>{
  let data:unknown;
  if(url.endsWith('/queue'))data=queue;
  else if(url.endsWith('/review')){const action=JSON.parse(String(init?.body));actions.push(action);queue=action.undo?[message]:[];data=queue;}
  else data={connected:true,last_success:1,revision};
  return {ok:true,status:200,json:async()=>data};
 });
 vi.stubGlobal('fetch',fetch);
 render(<DailyMail csrf="fixture" t={t} onUnauthorized={vi.fn()} onConnect={vi.fn()} onCreateTask={vi.fn()}/>);
 fireEvent.click(await screen.findByRole('button',{name:'Not now — next message'}));
 fireEvent.click(await screen.findByRole('button',{name:'Restore last message'}));
 await screen.findByRole('heading',{name:'Undo fixture'});
 expect(actions).toContainEqual({id:'undo-fixture',undo:true,revision:1});
 fireEvent.click(screen.getByRole('button',{name:'Not now — next message'}));
 await screen.findByRole('button',{name:'Restore last message'});
 revision=2;fireEvent(window,new Event('focus'));
 await waitFor(()=>expect(screen.queryByRole('button',{name:'Restore last message'})).not.toBeInTheDocument());
 revision=1;fireEvent(window,new Event('focus'));
 await waitFor(()=>expect(fetch.mock.calls.filter(([url])=>String(url).endsWith('/status')).length).toBeGreaterThanOrEqual(3));
 expect(screen.queryByRole('button',{name:'Restore last message'})).not.toBeInTheDocument();
});
