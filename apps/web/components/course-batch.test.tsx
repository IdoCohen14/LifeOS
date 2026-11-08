import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import {CourseBatchEntry} from './course-batch';
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
it('requires an explicit term and keeps confirmation separate from row entry',()=>{
 render(<CourseBatchEntry terms={[{id:'t',name:'Term fixture',start_date:'2026-10-01',end_date:'2027-01-01'}]} csrf="fixture" t={(_he,en)=>en} onChanged={vi.fn(async()=>{})} onUnauthorized={vi.fn()}/>);
 fireEvent.click(screen.getByRole('button',{name:'Add multiple courses'}));
 expect(screen.getByLabelText('Term')).toHaveValue('');
 expect(screen.getAllByLabelText(/Course name/)).toHaveLength(2);
 expect(screen.queryByRole('button',{name:/Confirm creation/})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Add another row'}));
 expect(screen.getAllByLabelText(/Course name/)).toHaveLength(3);
});
it('retains all edited rows when preview fails without issuing a save',async()=>{
 const fetch=vi.fn().mockResolvedValue({ok:false,status:503,json:async()=>({detail:'academic_busy'})});vi.stubGlobal('fetch',fetch);
 render(<CourseBatchEntry terms={[{id:'t',name:'Term fixture',start_date:'2026-10-01',end_date:'2027-01-01'}]} csrf="fixture" t={(_he,en)=>en} onChanged={vi.fn(async()=>{})} onUnauthorized={vi.fn()}/>);
 fireEvent.click(screen.getByRole('button',{name:'Add multiple courses'}));fireEvent.change(screen.getByLabelText('Term'),{target:{value:'t'}});fireEvent.change(screen.getByLabelText('Course name 1'),{target:{value:'First draft'}});fireEvent.change(screen.getByLabelText('Course name 2'),{target:{value:'Second draft'}});fireEvent.click(screen.getByRole('button',{name:'Review courses before saving'}));await screen.findByRole('alert');expect(screen.getByLabelText('Course name 1')).toHaveValue('First draft');expect(screen.getByLabelText('Course name 2')).toHaveValue('Second draft');expect(fetch).toHaveBeenCalledTimes(1);expect(fetch.mock.calls[0][0]).toBe('/api/academic/course-batches/preview');
});
