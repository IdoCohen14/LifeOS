import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import { PlanningNudge } from './planning-nudge';
vi.mock('@/lib/api',async original=>({...await original<typeof import('@/lib/api')>(),api:vi.fn()}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const suggestion={id:'fixture-suggestion',task_id:'fixture-task',title:'Assignment fixture',course_name:'Course fixture',due:'2026-11-09',start:'2026-11-04T08:00:00Z',end:'2026-11-04T08:30:00Z',duration:30,preferences_used:false};
const proposal={id:'fixture-proposal',record:{title:suggestion.title,start:suggestion.start,end:suggestion.end}};
const props=()=>({revision:0,csrf:'fixture',settings:{display_name:'',language:'en' as const,theme:'dark' as const,timezone:'Asia/Jerusalem'},t:(_he:string,en:string)=>en,disabled:false,onChanged:vi.fn(async()=>{}),onUnauthorized:vi.fn()});
it('only reads on display, reviews explicitly and requires a separate save',async()=>{
 vi.mocked(api).mockImplementation(async(path)=>path==='planning/suggestions'?{suggestion,stale_sources:[]}:path==='planning/suggestions/propose'?{proposal}:{});
 const p=props();render(<PlanningNudge {...p}/>);await screen.findByText('Assignment fixture · Course fixture');
 expect(vi.mocked(api).mock.calls.every(([,method])=>!method)).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'Review suggestion'}));await screen.findByRole('dialog');
 expect(vi.mocked(api).mock.calls.some(([path])=>path==='assistant/confirm')).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:'Confirm and save to calendar'}));
 await waitFor(()=>expect(api).toHaveBeenCalledWith('assistant/confirm','POST',{id:'fixture-proposal'},'fixture'));
 await waitFor(()=>expect(p.onChanged).toHaveBeenCalledOnce());
});
it('does not offer a slot for stale sources',async()=>{
 vi.mocked(api).mockResolvedValue({suggestion:null,reason:'stale_sources',stale_sources:['google']});render(<PlanningNudge {...props()}/>);
 await screen.findByText(/Waiting for current source/);expect(screen.queryByRole('button',{name:'Review suggestion'})).toBeNull();
});
it('persists snooze without creating or completing calendar/task records',async()=>{
 let muted=false;vi.mocked(api).mockImplementation(async(path)=>{if(path==='planning/suggestions/dismiss'){muted=true;return {};}return {suggestion:muted?null:suggestion,stale_sources:[]};});const p=props();const {rerender}=render(<PlanningNudge {...p}/>);await screen.findByText('Assignment fixture · Course fixture');
 fireEvent.click(screen.getByRole('button',{name:'Hide for 24 hours'}));
 await waitFor(()=>expect(screen.queryByText('Assignment fixture · Course fixture')).toBeNull());
 expect(api).toHaveBeenCalledWith('planning/suggestions/dismiss','POST',{id:'fixture-suggestion'},'fixture');
 expect(vi.mocked(api).mock.calls.some(([path])=>path==='assistant/confirm'||path==='tasks')).toBe(false);
 muted=false;rerender(<PlanningNudge {...p} revision={1}/>);await screen.findByText('Assignment fixture · Course fixture');
});
it('shows both times and explains that a move preserves the original until confirmation',async()=>{
 const moving={...suggestion,reason:'after_deadline',replacement:{id:'old',start:'2026-11-05T08:00:00Z',end:'2026-11-05T08:30:00Z'}};
 vi.mocked(api).mockImplementation(async(path)=>path==='planning/suggestions'?{suggestion:moving,stale_sources:[]}:{proposal});
 render(<PlanningNudge {...props()}/>);await screen.findByText('Consider moving your work time');
 fireEvent.click(screen.getByRole('button',{name:'Review suggestion'}));await screen.findByRole('dialog');
 expect(screen.getByText(/The original remains until confirmation/)).toBeVisible();expect(screen.getByText(/Previous time/)).toBeVisible();
 expect(vi.mocked(api).mock.calls.some(([path])=>path==='assistant/confirm')).toBe(false);
});
