import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import {MoodleUpdates} from './moodle-updates';
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
it('shows observed changes and routes to the actual source date',async()=>{
 const event={title:'Changed course fixture',start:'2026-11-02',end:'2026-11-03',all_day:true,source_url:'https://moodle27.braude.ac.il/calendar/view.php'};
 const fetch=vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>[{id:'fixture',kind:'changed',previous:{...event,start:'2026-11-01',end:'2026-11-02'},current:event,observed_at:1793232000}]});vi.stubGlobal('fetch',fetch);const onDay=vi.fn();
 render(<MoodleUpdates status={{configured:true,connected:true,state:'connected',error:null,syncing:false,stale:false,last_success:1793232000,event_count:1}} settings={{display_name:'',language:'en',theme:'dark',timezone:'Asia/Jerusalem'}} csrf="fixture" t={(_he,en)=>en} onUnauthorized={vi.fn()} onDay={onDay}/>);
 await screen.findByRole('heading',{name:'Changed course fixture'});expect(screen.getByText('Details changed')).toBeInTheDocument();expect(screen.getByText(/Before:/)).toBeInTheDocument();expect(screen.getByText(/Now:/)).toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'Open date in calendar'}));expect(onDay).toHaveBeenCalledWith('2026-11-02');expect(screen.getByRole('link',{name:'Moodle source'})).toHaveAttribute('href',event.source_url);expect(fetch.mock.calls[0][0]).toBe('/api/integrations/moodle/changes');
});
