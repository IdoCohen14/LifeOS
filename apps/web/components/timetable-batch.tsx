"use client";
import {useRef,useState,type FormEvent} from 'react';
import {CalendarPlus} from 'lucide-react';
import {api,ApiError} from '@/lib/api';
import type {Course,Term,Slot} from '@/lib/academic';
import type {Translate} from '@/lib/types';
import {Button} from './ui/button';
import {Modal} from './ui/dialog';
type Preview={id:string;course:Pick<Course,'id'|'name'|'term_id'>;term:Term;rows:Omit<Slot,'id'>[]};
const days=[['יום ראשון','Sunday'],['יום שני','Monday'],['יום שלישי','Tuesday'],['יום רביעי','Wednesday'],['יום חמישי','Thursday'],['יום שישי','Friday'],['שבת','Saturday']];
export function TimetableBatchEntry({courses,terms,csrf,t,onChanged,onUnauthorized}:{courses:Course[];terms:Term[];csrf:string;t:Translate;onChanged:()=>Promise<void>;onUnauthorized:()=>void}){
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[course,setCourse]=useState(''),[weekdays,setWeekdays]=useState<number[]>([]),[start,setStart]=useState('09:00'),[end,setEnd]=useState('10:00'),[zone,setZone]=useState('Asia/Jerusalem'),[location,setLocation]=useState(''),[preview,setPreview]=useState<Preview|null>(null),[saved,setSaved]=useState(false),[error,setError]=useState('');
 const generation=useRef(0);
 function failed(value:unknown){if(value instanceof ApiError&&value.status===401)onUnauthorized();setError(value instanceof ApiError?value.message:'unavailable');}
 async function discard(){if(preview&&!saved){try{await api(`academic/timetable-batches/${preview.id}`,'DELETE',undefined,csrf);}catch(value){if(value instanceof ApiError&&value.status===401)onUnauthorized();}}}
 function close(){if(busy&&!saved)return;void discard();generation.current++;setOpen(false);setBusy(false);setPreview(null);setSaved(false);setError('');}
 async function propose(event:FormEvent){event.preventDefault();if(!weekdays.length)return;setBusy(true);setError('');try{setPreview(await api<Preview>('academic/timetable-batches/preview','POST',{course_id:course,weekdays,start_time:start,end_time:end,timezone:zone,location},csrf));}catch(value){failed(value);}finally{setBusy(false);}}
 async function confirm(){if(!preview||busy||saved)return;const current=generation.current;setBusy(true);setError('');try{await api(`academic/timetable-batches/${preview.id}/confirm`,'POST',undefined,csrf);setSaved(true);setWeekdays([]);try{await onChanged();}catch{if(generation.current===current)setError('refresh');}}catch(value){if(generation.current===current)failed(value);}finally{if(generation.current===current)setBusy(false);}}
 return <><Button variant="secondary" disabled={!courses.length||busy} onClick={()=>{generation.current++;setOpen(true);}}><CalendarPlus size={16} aria-hidden="true"/>{t('הוספת מפגשים שבועיים','Add weekly meetings')}</Button>
 {open&&<Modal open onClose={close} title={t('הוספת מפגשים שבועיים','Add weekly meetings')} description={t('בחרו ימים עם אותן שעות ומיקום. רק אישור הסקירה שומר את המפגשים.','Choose days with the same hours and location. Only confirming the review saves meetings.')} closeLabel={t('סגירה','Close')}>
 {!preview?<form className="form-stack" onSubmit={propose}><fieldset className="planner-fields" disabled={busy}>
 <label>{t('קורס','Course')}<select aria-label={t('קורס','Course')} required value={course} onChange={e=>setCourse(e.target.value)}><option value="">{t('בחרו קורס','Choose a course')}</option>{courses.map(c=><option key={c.id} value={c.id}>{c.name}{c.code?` · ${c.code}`:''} · {terms.find(term=>term.id===c.term_id)?.name??t('סמסטר לא זמין','Term unavailable')}</option>)}</select></label>
 <fieldset className="batch-course-row"><legend>{t('ימי המפגש','Meeting days')}</legend><div className="weekday-picker">{[0,1,2,3,4,5,6].map(day=><label className="notification-check" key={day}><input type="checkbox" checked={weekdays.includes(day)} onChange={e=>setWeekdays(current=>e.target.checked?[...current,day]:current.filter(value=>value!==day))}/>{t(days[day][0],days[day][1])}</label>)}</div></fieldset>
 <div className="form-grid"><label>{t('שעת התחלה','Start time')}<input type="time" required value={start} onChange={e=>setStart(e.target.value)}/></label><label>{t('שעת סיום','End time')}<input type="time" required value={end} onChange={e=>setEnd(e.target.value)}/></label></div>
 <label>{t('אזור זמן','Time zone')}<input dir="ltr" required maxLength={100} value={zone} onChange={e=>setZone(e.target.value)}/></label><label>{t('מיקום','Location')}<input maxLength={240} value={location} onChange={e=>setLocation(e.target.value)}/></label>
 </fieldset><Button type="submit" disabled={busy||!course||!weekdays.length}>{t('סקירת המפגשים לפני שמירה','Review meetings before saving')}</Button></form>:<div className="form-stack batch-course-review">
 <h3 dir="auto">{preview.course.name} · {preview.term.name}</h3><p className="field-help"><bdi>{preview.term.start_date} — {preview.term.end_date}</bdi></p>
 <ul className="batch-review">{preview.rows.map(row=><li key={row.weekday}><strong>{t(days[row.weekday][0],days[row.weekday][1])}</strong><p><bdi>{row.start_time} — {row.end_time} · {row.timezone}</bdi></p>{row.location&&<p dir="auto">{row.location}</p>}</li>)}</ul>
 <p className="field-help">{t('תבנית שבועית לתקופת הסמסטר; אין הסקה אוטומטית של חגים או ביטולים.','Weekly template for the term; holidays and cancellations are not inferred.')}</p>
 {saved?<p role="status">{t(`נוצרו ${preview.rows.length} מפגשים שבועיים.`,`Created ${preview.rows.length} weekly meetings.`)}</p>:<div className="form-actions"><Button disabled={busy} onClick={()=>void confirm()}>{t(`אישור יצירת ${preview.rows.length} מפגשים`,`Confirm creation of ${preview.rows.length} meetings`)}</Button><Button variant="ghost" disabled={busy} onClick={async()=>{setBusy(true);await discard();setPreview(null);setError('');setBusy(false);}}>{t('חזרה לעריכה','Back to editing')}</Button></div>}
 </div>}
 {error&&<p role="alert" className="error-message">{error==='refresh'?t('המפגשים נשמרו, אך יש לרענן את התצוגה.','Meetings were saved, but the view needs refreshing.'):error==='timetable_batch_duplicate'?t('מפגש באותו יום ובאותן שעות כבר קיים בקורס. בדקו את הימים שנבחרו.','A meeting on the same day and hours already exists for this course. Check the selected days.'):t('לא ניתן להשלים. בדקו את הקורס, הימים והשעות. אם הסקירה פגה או שהמידע השתנה, חזרו לעריכה ובקשו סקירה חדשה.','Could not finish. Check the course, days and hours. If the review expired or data changed, return to editing and request a new review.')}</p>}
 </Modal>}</>;
}
