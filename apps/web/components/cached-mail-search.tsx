"use client";
import {useState} from 'react';
import {Search} from 'lucide-react';
import {api,ApiError} from '@/lib/api';
import type {Translate} from '@/lib/types';
import {Button} from './ui/button';
type Message={id:string;subject:string;sender:string;snippet:string;source_url:string;cached_thread_count?:number};
export function CachedMailSearch({t,onUnauthorized}:{t:Translate;onUnauthorized:()=>void}){
 const [open,setOpen]=useState(false),[messages,setMessages]=useState<Message[]|null>(null),[query,setQuery]=useState(''),[index,setIndex]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState(false);
 async function load(){setBusy(true);setError(false);try{setMessages(await api<Message[]>('integrations/gmail/messages'));setIndex(0);}catch(value){if(value instanceof ApiError&&value.status===401)onUnauthorized();setError(true);}finally{setBusy(false);}}
 const words=query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
 const matches=words.length?(messages??[]).filter(message=>{const text=`${message.subject} ${message.sender} ${message.snippet}`.toLocaleLowerCase();return words.every(word=>text.includes(word));}):[];
 const message=matches[index];
 return <div className="cached-mail-search"><Button variant="ghost" size="small" aria-expanded={open} onClick={()=>{setOpen(!open);if(!open&&messages===null&&!busy)void load();}}><Search size={15} aria-hidden="true"/>{t('חיפוש במיילים שסונכרנו','Search synchronized mail')}</Button>
 {open&&<div className="form-stack"><p className="field-help">{t('חיפוש מקומי במיילים הרלוונטיים מתוך 50 הודעות הדואר הנכנס האחרונות שסונכרנו. כולל הודעות שכבר עברתם עליהן; ללא חיפוש בכל תיבת Gmail או בגוף המלא. תור המיילים החדשים אינו משתנה.','Local search of relevant mail from the latest 50 synchronized Inbox messages, including reviewed mail. This does not search your whole Gmail mailbox or full message bodies. Your new-mail queue stays unchanged.')}</p>
 <label>{t('חיפוש בנושא, בשולח או בטקסט','Search subject, sender or text')}<input type="search" maxLength={200} value={query} onChange={event=>{setQuery(event.target.value);setIndex(0);}}/></label>
 {busy&&<p role="status">{t('טוען מיילים שמורים…','Loading cached mail…')}</p>}
 {error&&<p role="alert">{t('לא ניתן לטעון כעת. תוצאות קודמות עשויות להיות לא מעודכנות.','Unable to load now. Previous results may be outdated.')}</p>}
 <Button size="small" variant="secondary" disabled={busy} onClick={()=>void load()}>{t('רענון תוצאות שמורות','Refresh cached results')}</Button>
 {!busy&&messages!==null&&(words.length?message?<article className="gmail-message" aria-live="polite"><p className="field-help">{t(`תוצאה ${index+1} מתוך ${matches.length}`,`Result ${index+1} of ${matches.length}`)}</p><h3 dir="auto">{message.subject||t('ללא נושא','No subject')}</h3><p dir="auto">{message.sender}</p>{(message.cached_thread_count??0)>1&&<p className="field-help">{t(`בשיחה הזו ${message.cached_thread_count} הודעות רלוונטיות בסנכרון הנוכחי, כולל הודעות שכבר נקראו או נבדקו.`,`This conversation has ${message.cached_thread_count} relevant messages in the current snapshot, including read or reviewed messages.`)}</p>}<p dir="auto">{message.snippet}</p><div className="google-actions"><Button size="small" variant="ghost" disabled={index===0} onClick={()=>setIndex(value=>value-1)}>{t('תוצאה קודמת','Previous result')}</Button><Button size="small" variant="ghost" disabled={index>=matches.length-1} onClick={()=>setIndex(value=>value+1)}>{t('תוצאה הבאה','Next result')}</Button><a className="text-button" href={message.source_url} target="_blank" rel="noopener noreferrer">{t('פתיחה ב־Gmail','Open in Gmail')}</a></div></article>:<p role="status">{t('לא נמצאו תוצאות במיילים הרלוונטיים שסונכרנו.','No matches in synchronized relevant mail.')}</p>:<p className="field-help">{t('הקלידו מילים לחיפוש.','Enter words to search.')}</p>)}
 </div>}</div>;
}
