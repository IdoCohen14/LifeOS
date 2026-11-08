"use client";
import {useRef,useState,type FormEvent} from 'react';
import {Plus,Trash2} from 'lucide-react';
import {api,ApiError} from '@/lib/api';
import type {Term} from '@/lib/academic';
import type {Translate} from '@/lib/types';
import {Button} from './ui/button';
import {Modal} from './ui/dialog';
type Row={name:string;code:string;instructor:string;credits:number;color:string};
type Preview={id:string;term:Term;rows:Row[]};
const blank=():Row=>({name:'',code:'',instructor:'',credits:0,color:'#a597ff'});
export function CourseBatchEntry({terms,initialTerm,csrf,t,onChanged,onUnauthorized}:{terms:Term[];initialTerm?:string;csrf:string;t:Translate;onChanged:()=>Promise<void>;onUnauthorized:()=>void}){
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[rows,setRows]=useState<Row[]>([blank(),blank()]),[term,setTerm]=useState(''),[preview,setPreview]=useState<Preview|null>(null),[saved,setSaved]=useState(false),[error,setError]=useState('');
 const generation=useRef(0);
 function failed(value:unknown){if(value instanceof ApiError&&value.status===401)onUnauthorized();setError(value instanceof ApiError?value.message:'unavailable');}
 async function discard(){if(preview&&!saved){try{await api(`academic/course-batches/${preview.id}`,'DELETE',undefined,csrf);}catch(value){if(value instanceof ApiError&&value.status===401)onUnauthorized();}}}
 function close(){if(busy&&!saved)return;void discard();generation.current++;setOpen(false);setBusy(false);setPreview(null);setSaved(false);setError('');}
 async function propose(event:FormEvent){event.preventDefault();setBusy(true);setError('');try{setPreview(await api<Preview>('academic/course-batches/preview','POST',{term_id:term,rows},csrf));}catch(value){failed(value);}finally{setBusy(false);}}
 async function confirm(){if(!preview||busy||saved)return;const current=generation.current;setBusy(true);setError('');try{await api(`academic/course-batches/${preview.id}/confirm`,'POST',undefined,csrf);setSaved(true);setRows([blank(),blank()]);try{await onChanged();}catch{if(generation.current===current)setError('refresh');}}catch(value){if(generation.current===current)failed(value);}finally{if(generation.current===current)setBusy(false);}}
 function update(index:number,value:Partial<Row>){setRows(current=>current.map((row,i)=>i===index?{...row,...value}:row));}
 return <>
  <Button variant="secondary" disabled={!terms.length||busy} onClick={()=>{generation.current++;if(!term&&terms.some(value=>value.id===initialTerm))setTerm(initialTerm!);setOpen(true);}}><Plus size={16} aria-hidden="true"/>{t('הוספת כמה קורסים','Add multiple courses')}</Button>
  {open&&<Modal open onClose={close} title={t('הוספת כמה קורסים','Add multiple courses')} description={t('עד 20 קורסים לסמסטר אחד. רק אישור הסקירה שומר את הקורסים.','Up to 20 courses in one term. Only confirming the review saves courses.')} closeLabel={t('סגירה','Close')}>
   {!preview?<form className="form-stack" onSubmit={propose}><fieldset disabled={busy} className="planner-fields">
    <label>{t('סמסטר','Term')}<select aria-label={t('סמסטר','Term')} value={term} onChange={event=>setTerm(event.target.value)} required><option value="">{t('בחרו סמסטר','Choose a term')}</option>{terms.map(value=><option key={value.id} value={value.id}>{value.name}</option>)}</select></label>
    <p className="field-help">{t('הזינו שם בכל שורה. מחקו שורות שאינן נחוצות. שמות וקודים כפולים באותו סמסטר לא יישמרו.','Enter a name in every row. Remove unused rows. Duplicate names or codes in the same term are rejected.')}</p>
    {rows.map((row,index)=><fieldset className="batch-course-row" key={index}><legend>{t(`קורס ${index+1}`,`Course ${index+1}`)}</legend>
     <label>{t(`שם הקורס ${index+1}`,`Course name ${index+1}`)}<input value={row.name} onChange={event=>update(index,{name:event.target.value})} required maxLength={160}/></label>
     <div className="form-grid"><label>{t(`קוד קורס ${index+1}`,`Course code ${index+1}`)}<input value={row.code} onChange={event=>update(index,{code:event.target.value})} maxLength={50}/></label><label>{t(`נקודות זכות ${index+1}`,`Credits ${index+1}`)}<input type="number" min={0} max={60} step="0.5" value={row.credits} onChange={event=>update(index,{credits:Number(event.target.value)})}/></label></div>
     <label>{t(`מרצה ${index+1}`,`Instructor ${index+1}`)}<input value={row.instructor} onChange={event=>update(index,{instructor:event.target.value})} maxLength={120}/></label>
     <Button type="button" variant="ghost" disabled={rows.length===1} onClick={()=>setRows(current=>current.filter((_,i)=>i!==index))}><Trash2 size={14} aria-hidden="true"/>{t(`הסרת שורה ${index+1}`,`Remove row ${index+1}`)}</Button>
    </fieldset>)}
    <Button type="button" variant="secondary" disabled={rows.length>=20} onClick={()=>setRows(current=>[...current,blank()])}>{t('הוספת שורה','Add another row')}</Button>
   </fieldset><Button type="submit" disabled={busy}>{t('סקירת הקורסים לפני שמירה','Review courses before saving')}</Button></form>:<div className="form-stack batch-course-review">
    <h3 dir="auto">{preview.term.name}</h3><p className="field-help"><bdi>{preview.term.start_date} — {preview.term.end_date}</bdi></p>
    <ul className="batch-review">{preview.rows.map((row,index)=><li key={index}><strong dir="auto">{row.name}</strong><p className="field-help" dir="auto">{[row.code,row.instructor,`${row.credits} ${t('נק״ז','credits')}`].filter(Boolean).join(' · ')}</p></li>)}</ul>
    {saved?<p role="status">{t(`נוצרו ${preview.rows.length} קורסים בסמסטר שנבחר.`,`Created ${preview.rows.length} courses in the selected term.`)}</p>:<div className="form-actions"><Button disabled={busy} onClick={()=>void confirm()}>{t(`אישור יצירת ${preview.rows.length} קורסים`,`Confirm creation of ${preview.rows.length} courses`)}</Button><Button variant="ghost" disabled={busy} onClick={async()=>{setBusy(true);await discard();setPreview(null);setError('');setBusy(false);}}>{t('חזרה לעריכה','Back to editing')}</Button></div>}
   </div>}
   {error&&<p role="alert" className="error-message">{error==='refresh'?t('הקורסים נשמרו, אך יש לרענן את התצוגה.','Courses were saved, but the view needs refreshing.'):error==='course_batch_duplicate'?t('יש שמות או קודים כפולים ברשימה או בסמסטר. בדקו את השורות ואת הקורסים הקיימים.','Duplicate names or codes exist in the list or term. Check your rows and existing courses.'):t('לא ניתן להשלים כרגע. בדקו את הסמסטר והשורות; אם הסקירה פגה או שהמידע השתנה, חזרו לעריכה ובקשו סקירה חדשה.','Could not finish. Check the term and rows; if the review expired or data changed, return to editing and request a new review.')}</p>}
  </Modal>}
 </>;
}
