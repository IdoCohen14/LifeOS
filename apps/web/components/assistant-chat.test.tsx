import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {createRef} from 'react';
import type {AssistantChatHandle} from '@/lib/assistant-requests';
import {api,ApiError} from '@/lib/api';
import {AssistantChat} from './assistant-chat';

vi.mock('@/lib/api',async original=>({...await original<typeof import('@/lib/api')>(),api:vi.fn()}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const settings={display_name:'',language:'en' as const,theme:'dark' as const,timezone:'Asia/Jerusalem'};

it.each([
 [429,'assistant_busy','The assistant is handling another request. Wait a moment and try again.'],
 [409,'Request changed; refresh','The request or its information changed. Refresh it before trying again.'],
 [404,'Request not found','This request is no longer available. Return to general chat to continue.'],
])('explains chat status %s without claiming the model is disconnected',async(status,code,copy)=>{
 vi.mocked(api).mockImplementation(async(path)=>{
  if(path==='assistant/status')return {ready:true,model:'fixture',local:true,state:'ready'};
  if(path==='assistant/history')return {enabled:false,generation:0,stored_count:0,available_turns:0,truncated:false,messages:[]};
  if(path==='assistant/chat')throw new ApiError(status,code);
  throw Error('Unexpected fixture API '+path);
 });
 const ref=createRef<AssistantChatHandle>();
 render(<AssistantChat ref={ref} csrf="fixture" settings={settings} t={(_he,en)=>en} onChanged={vi.fn(async()=>{})} onUnauthorized={vi.fn()}/>);
 act(()=>{ref.current!.openRequest({id:'00000000-0000-0000-0000-000000000001',title:'Tracked fixture',course_name:'',due:null,status:'waiting_user',version:1,created_at:'2026-11-04T00:00:00Z',updated_at:'2026-11-04T00:00:00Z',followup_at:null});});
 const input=await screen.findByRole('textbox',{name:'Message the assistant'});
 fireEvent.change(input,{target:{value:'Add a task on 2026-11-09'}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Send message'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 expect(await screen.findByRole('alert')).toHaveTextContent(copy);
 expect(input).toHaveValue('Add a task on 2026-11-09');
 expect(screen.getByRole('button',{name:'Send message'})).toBeEnabled();
 if(status===404){fireEvent.click(screen.getByRole('button',{name:'Return to general chat'}));expect(screen.queryByRole('alert')).toBeNull();expect(input).toHaveValue('Add a task on 2026-11-09');}
});
