"use client";
import {useCallback,useEffect,useState} from 'react';
import {GraduationCap} from 'lucide-react';
import {api,ApiError} from '@/lib/api';
import {formatDay,shiftDay} from '@/lib/dates';
import type {Settings,Translate} from '@/lib/types';
import type {MoodleStatus} from './moodle-settings';
import {Button} from './ui/button';
type Event={title:string;start:string;end:string;all_day:boolean;source_url:string|null};
type Change={id:string;kind:'added'|'changed'|'removed';previous:Event|null;current:Event|null;observed_at:number};
export function MoodleUpdates({status,settings,csrf,t,onUnauthorized,onDay}:{status:MoodleStatus;settings:Settings;csrf:string;t:Translate;onUnauthorized:()=>void;onDay:(start:string)=>void}){
 const [items,setItems]=useState<Change[]|null>(null),[error,setError]=useState(false),[busy,setBusy]=useState(true),[expanded,setExpanded]=useState(false);
 const load=useCallback(async()=>{try{const values=await api<Change[]>('integrations/moodle/changes');setItems(values);setError(false);}catch(value){if(value instanceof ApiError&&value.status===401)onUnauthorized();setError(true);}finally{setBusy(false);}},[onUnauthorized]);
 useEffect(()=>{void(async()=>{await load();})();},[load,csrf,status.last_success]);
 const format=(value:string)=>value.length===10?formatDay(value,settings.language,{day:'numeric',month:'short',year:'numeric'}):new Intl.DateTimeFormat(settings.language,{dateStyle:'short',timeStyle:'short',timeZone:settings.timezone}).format(new Date(value));
 const range=(event:Event)=>event.all_day?format(event.start)+(shiftDay(event.end,-1)!==event.start?` — ${format(shiftDay(event.end,-1))}`:''):`${format(event.start)} — ${format(event.end)}`;
 return <section className="panel moodle-updates" aria-label={t('עדכוני Moodle אחרונים','Recent Moodle updates')}><div className="panel-heading"><div className="heading-with-icon"><GraduationCap size={20} aria-hidden="true"/><h2>{t('עדכוני Moodle אחרונים','Recent Moodle updates')}</h2></div><Button variant="ghost" size="small" disabled={busy} onClick={()=>{setBusy(true);void load();}}>{t('רענון העדכונים השמורים','Refresh cached updates')}</Button></div>
 <p className="field-help">{t('שינויים שזוהו בין סנכרונים מוצלחים. הזמן המוצג הוא זמן הזיהוי באפליקציה, ולא מועד הפרסום במכללה. היעלמות מהייצוא אינה בהכרח ביטול.','Changes observed between successful syncs. Times show when LifeOS observed the change, not publication time. Disappearance from the export does not necessarily mean cancellation.')}</p>
 {(error||status.stale||status.error)&&<p role="alert" className="error-message">{t('העדכונים השמורים עשויים להיות לא מעודכנים. בדקו את מצב הסנכרון בהגדרות.','Cached updates may be outdated. Check synchronization in Settings.')}</p>}
 {items===null&&busy&&<p role="status">{t('טוען עדכונים…','Loading updates…')}</p>}
 {items?.length===0&&<p role="status">{status.last_success?t('עדיין לא זוהו שינויים בין הסנכרונים.','No changes have been observed between syncs yet.'):t('ממתין לסנכרון ראשון; הוא ישמש כנקודת התחלה.','Waiting for the first sync, which establishes the baseline.')}</p>}
 <ul className="moodle-updates-list">{(expanded?items:items?.slice(0,3))?.map(item=>{const event=item.current??item.previous;if(!event)return null;return <li key={item.id}><span className="subtle-badge">{item.kind==='added'?t('נוסף לייצוא','Added to export'):item.kind==='changed'?t('הפרטים השתנו','Details changed'):t('לא נמצא בייצוא האחרון','Absent from latest export')}</span><h3 dir="auto">{event.title}</h3><p className="field-help">{t('זוהה: ','Observed: ')}{new Intl.DateTimeFormat(settings.language,{dateStyle:'short',timeStyle:'short',timeZone:settings.timezone}).format(new Date(item.observed_at*1000))}</p>
 {item.previous&&item.current?<><p>{t('קודם: ','Before: ')}<bdi>{range(item.previous)}</bdi>{item.previous.title!==item.current.title&&<> · <bdi>{item.previous.title}</bdi></>}</p><p>{t('כעת: ','Now: ')}<bdi>{range(item.current)}</bdi></p></>:<p><bdi>{range(event)}</bdi></p>}
 <div className="google-actions"><Button variant="secondary" size="small" onClick={()=>onDay(event.start)}>{t('פתיחת התאריך ביומן','Open date in calendar')}</Button>{event.source_url&&<a className="text-button" href={event.source_url} target="_blank" rel="noopener noreferrer">{t('המקור ב־Moodle','Moodle source')}</a>}</div></li>;})}</ul>
 {(items?.length??0)>3&&<Button variant="ghost" size="small" onClick={()=>setExpanded(!expanded)}>{expanded?t('הצגת פחות','Show fewer'):t(`הצגת ${items!.length} העדכונים האחרונים`,`Show ${items!.length} recent updates`)}</Button>}
 <p className="field-help">{t('מוצגים עד 20 עדכונים. ההיסטוריה המקומית נשמרת עד 30 יום או 200 שינויים, ונמחקת בניתוק או בהחלפת החיבור.','Shows up to 20 updates. Local history keeps up to 30 days or 200 changes and clears when disconnecting or replacing the connection.')}</p>
 </section>;
}
