import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import {TimetableBatchEntry} from './timetable-batch';
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
it('requires a course and selected days before requesting a review',()=>{
 render(<TimetableBatchEntry terms={[{id:"t",name:"Autumn fixture",start_date:"2026-10-01",end_date:"2027-01-01"}]} courses={[{id:'c',term_id:'t',name:'Fixture',code:'',instructor:'',credits:0,color:'#ffffff'}]} csrf="fixture" t={(_he,en)=>en} onChanged={vi.fn(async()=>{})} onUnauthorized={vi.fn()}/>);
 fireEvent.click(screen.getByRole('button',{name:'Add weekly meetings'}));
 expect(screen.getByLabelText('Course')).toHaveValue('');
 expect(screen.getByRole('option',{name:'Fixture · Autumn fixture'})).toHaveValue('c');
 expect(screen.getAllByRole('checkbox')).toHaveLength(7);
 expect(screen.getByRole('button',{name:'Review meetings before saving'})).toBeDisabled();
 fireEvent.change(screen.getByLabelText('Course'),{target:{value:'c'}});
 fireEvent.click(screen.getByLabelText('Monday'));
 expect(screen.getByRole('button',{name:'Review meetings before saving'})).toBeEnabled();
 expect(screen.queryByRole('button',{name:/Confirm creation/})).not.toBeInTheDocument();
});
it('sends Sunday-based weekdays matching academic calendar projection',async()=>{
 const fetch=vi.fn().mockResolvedValue({ok:false,status:503,json:async()=>({detail:'academic_busy'})});vi.stubGlobal('fetch',fetch);
 render(<TimetableBatchEntry terms={[{id:"t",name:"Autumn fixture",start_date:"2026-10-01",end_date:"2027-01-01"}]} courses={[{id:'c',term_id:'t',name:'Fixture',code:'',instructor:'',credits:0,color:'#ffffff'}]} csrf="fixture" t={(_he,en)=>en} onChanged={vi.fn(async()=>{})} onUnauthorized={vi.fn()}/>);
 fireEvent.click(screen.getByRole('button',{name:'Add weekly meetings'}));fireEvent.change(screen.getByLabelText('Course'),{target:{value:'c'}});fireEvent.click(screen.getByLabelText('Monday'));fireEvent.click(screen.getByLabelText('Wednesday'));fireEvent.click(screen.getByRole('button',{name:'Review meetings before saving'}));await screen.findByRole('alert');expect(JSON.parse(fetch.mock.calls[0][1].body).weekdays).toEqual([1,3]);expect(screen.getByLabelText('Monday')).toBeChecked();
});
