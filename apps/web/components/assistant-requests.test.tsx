import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import { AssistantRequests } from './assistant-requests';
vi.mock('@/lib/api', async original => ({...await original<typeof import('@/lib/api')>(), api:vi.fn()}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const item={id:'fixture',title:'Request fixture',course_name:'Course fixture',due:'2026-11-09',status:'waiting_user' as const,version:3,created_at:'2026-11-04T00:00:00Z',updated_at:'2026-11-04T00:00:00Z',followup_at:null};
const props=()=>({csrf:'fixture',revision:0,settings:{display_name:'',language:'en' as const,theme:'dark' as const,timezone:'Asia/Jerusalem'},t:(_he:string,en:string)=>en,onOpen:vi.fn(),onChanged:vi.fn(async()=>{}),onUnauthorized:vi.fn()});
it('opens context only on user action and sends versioned follow-up without changing a task',async()=>{
 vi.mocked(api).mockResolvedValue({items:[item]});const p=props();render(<AssistantRequests {...p}/>);
 await waitFor(()=>expect(screen.getByText('My requests')).toBeInTheDocument());
 fireEvent.click(screen.getByText('My requests'));
 await screen.findByText('Request fixture · Course fixture');expect(p.onOpen).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'Continue with assistant'}));expect(p.onOpen).toHaveBeenCalledWith(item);
 fireEvent.click(screen.getByRole('button',{name:'Follow up in an hour'}));
 await waitFor(()=>expect(api).toHaveBeenCalledWith('assistant/requests/fixture','PATCH',{version:3,followup_minutes:60},'fixture'));
 expect(vi.mocked(api).mock.calls.every(([path])=>!path.startsWith('tasks'))).toBe(true);
});
it('requires explicit confirmation before removing tracking',async()=>{
 vi.mocked(api).mockResolvedValue({items:[item]});render(<AssistantRequests {...props()}/>);
 fireEvent.click(screen.getByText('My requests'));await screen.findByText('Request fixture · Course fixture');
 fireEvent.click(screen.getByRole('button',{name:'Remove tracking'}));
 expect(vi.mocked(api).mock.calls.some(([,method])=>method==='DELETE')).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:'Confirm removal'}));
 await waitFor(()=>expect(api).toHaveBeenCalledWith('assistant/requests/fixture','DELETE',{version:3},'fixture'));
});
