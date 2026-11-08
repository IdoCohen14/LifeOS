import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {api,ApiError} from '@/lib/api';
import {SecretarySettings} from './secretary-settings';
vi.mock('@/lib/api',async original=>({...await original<typeof import('@/lib/api')>(),api:vi.fn()}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const values={proactive_enabled:true,suggestion_snooze_minutes:1440 as const,request_followup_minutes:0 as const,reply_style:'brief' as const,push_daily_limit:0 as const,class_reminder_minutes:0 as const};
const props=()=>({csrf:'fixture',t:(_he:string,en:string)=>en,onChanged:vi.fn(async()=>{}),onUnauthorized:vi.fn()});
it('saves explicit versioned preferences without enabling conversation history',async()=>{
 vi.mocked(api).mockImplementation(async(_path,method)=>({revision:method==='PUT'?1:0,values}));
 render(<SecretarySettings {...props()}/>);const select=await screen.findByRole('combobox',{name:'Daily Push allowance per device'});fireEvent.change(select,{target:{value:'3'}});
 fireEvent.click(screen.getByRole('button',{name:'Save secretary preferences'}));
 await waitFor(()=>expect(api).toHaveBeenCalledWith('assistant/preferences','PUT',{...values,push_daily_limit:3,revision:0},'fixture'));
 await screen.findByText('Preferences saved.');expect(vi.mocked(api).mock.calls.every(([path])=>path==='assistant/preferences')).toBe(true);
});
it('keeps the chosen values visible on conflict and requires refresh instead of claiming save',async()=>{
 vi.mocked(api).mockImplementation(async(_path,method)=>{if(method==='PUT')throw new ApiError(409,'changed');return {revision:0,values};});render(<SecretarySettings {...props()}/>);
 const select=await screen.findByRole('combobox',{name:'Daily Push allowance per device'});fireEvent.change(select,{target:{value:'6'}});fireEvent.click(screen.getByRole('button',{name:'Save secretary preferences'}));
 await screen.findByText(/Save did not complete/);expect(select).toHaveValue('6');expect(screen.queryByText('Preferences saved.')).toBeNull();
});
