import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
import { PersonalUpdates } from './personal-updates';
import type { NotificationFeed } from './notification-center';
afterEach(cleanup);
const feed:NotificationFeed={items:[{id:'one',kind:'due_soon',title:'First task',course_name:'Course',due:'2026-11-04',target:'tasks',source_ids:['task'],read:false},{id:'two',kind:'overdue',title:'Second task',target:'tasks',source_ids:['task2'],read:false}],unread:2,truncated:false,conflicts_limited:false,quiet:false,stale_sources:[],preferences:{enabled:true,tasks:true,conflicts:true,quiet_enabled:false,quiet_start:'22:00',quiet_end:'07:00'}};
const props=()=>({data:feed,now:new Date('2026-11-03T08:00:00Z'),settings:{display_name:'',language:'en' as const,theme:'dark' as const,timezone:'Asia/Jerusalem'},t:(_he:string,en:string)=>en,onOpen:vi.fn(),onShowAll:vi.fn(),onRead:vi.fn(async()=>{}),onAction:vi.fn(async()=>{}),onRefresh:vi.fn(async()=>{}),onUnauthorized:vi.fn()});
it('shows one contextual update and never completes the task through seen or snooze',async()=>{
 const p=props();render(<PersonalUpdates {...p}/>);
 expect(screen.getByText('First task · Course')).toBeVisible();expect(screen.queryByText('Second task')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Open task'}));expect(p.onOpen).toHaveBeenCalledWith(feed.items[0]);
 fireEvent.click(screen.getByRole('button',{name:'Seen'}));await waitFor(()=>expect(p.onRead).toHaveBeenCalledWith(['one']));
 await waitFor(()=>expect(screen.getByRole('button',{name:'In an hour'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'In an hour'}));await waitFor(()=>expect(p.onAction).toHaveBeenCalledWith({id:'one',action:'snooze',minutes:60}));
});
it('distinguishes unavailable, disabled and empty feeds',()=>{
 const p=props();const {rerender}=render(<PersonalUpdates {...p} data={null}/>);expect(screen.getByText('Updates could not be loaded right now.')).toBeVisible();
 rerender(<PersonalUpdates {...p} data={{...feed,preferences:{...feed.preferences,enabled:false}}}/>);expect(screen.getByText(/Updates are off/)).toBeVisible();
 rerender(<PersonalUpdates {...p} data={{...feed,items:[],unread:0}}/>);expect(screen.getByText(/No new updates/)).toBeVisible();
});
it('keeps the update on failure and reports session expiry without optimistic dismissal',async()=>{
 const p=props();p.onRead.mockRejectedValueOnce(new ApiError(401,'expired'));render(<PersonalUpdates {...p}/>);fireEvent.click(screen.getByRole('button',{name:'Seen'}));
 await screen.findByRole('alert');expect(p.onUnauthorized).toHaveBeenCalledOnce();expect(screen.getByText('First task · Course')).toBeVisible();
});
it('keeps stale information explicit and disables receipt changes when disconnected',()=>{
 render(<PersonalUpdates {...props()} disabled/>);expect(screen.getByRole('status')).toHaveTextContent(/outdated/);expect(screen.getByRole('button',{name:'Seen'})).toBeDisabled();
});
