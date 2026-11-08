"use client";
import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import type { Translate } from "@/lib/types";
import { Button } from "./ui/button";

type Values = { proactive_enabled:boolean; suggestion_snooze_minutes:60|1440; request_followup_minutes:0|60|1440; reply_style:"brief"|"standard"; push_daily_limit:0|3|6|10; class_reminder_minutes?:0|10|15|30 };
type State = {revision:number;values:Values};

export function SecretarySettings({csrf,t,onChanged,onUnauthorized}:{csrf:string;t:Translate;onChanged:()=>Promise<void>;onUnauthorized:()=>void}) {
  const [state,setState] = useState<State|null>(null);
  const [busy,setBusy] = useState(false);
  const [message,setMessage] = useState("");
  const [reload,setReload] = useState(0);
  useEffect(()=>{
    let active=true;
    api<State>("assistant/preferences").then(value=>{if(active){setState(value);setMessage("");}}).catch(error=>{
      if(!active)return;if(error instanceof ApiError && error.status===401)onUnauthorized();setMessage(t("ההעדפות לא נטענו. אפשר לרענן.","Preferences could not load. Try refreshing."));
    });return()=>{active=false;};
  },[reload,onUnauthorized,t]);
  async function save(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();if(!state||busy)return;const data=new FormData(event.currentTarget);setBusy(true);setMessage("");
    const values={proactive_enabled:data.get('proactive_enabled')==='on',suggestion_snooze_minutes:Number(data.get('suggestion_snooze_minutes')),request_followup_minutes:Number(data.get('request_followup_minutes')),reply_style:String(data.get('reply_style')),push_daily_limit:Number(data.get('push_daily_limit')),class_reminder_minutes:Number(data.get('class_reminder_minutes'))};
    try{setState(await api<State>('assistant/preferences','PUT',{...values,revision:state.revision},csrf));setMessage(t("ההעדפות נשמרו.","Preferences saved."));try{await onChanged();}catch{setMessage(t("ההעדפות נשמרו. רעננו את האתר כדי לראות את השינוי.","Preferences saved. Refresh to see the change."));}}
    catch(error){if(error instanceof ApiError&&error.status===401)onUnauthorized();setMessage(t("השמירה לא הושלמה או שההעדפות השתנו בלשונית אחרת. רעננו לפני ניסיון נוסף.","Save did not complete or preferences changed in another tab. Refresh before retrying."));}finally{setBusy(false);}
  }
  return <div className="form-stack secretary-settings">
    <p className="field-help">{t("אתם בוחרים את ההעדפות שנזכרות. הן נשמרות בחשבון וניתנות לעריכה; אין הסקת עובדות אישיות מתוך השיחה.","You choose which preferences are remembered. They stay editable in your account; conversation text is not treated as verified personal facts.")}</p>
    {state&&<form key={state.revision} className="form-stack" onSubmit={save}>
      <label className="checkbox-label"><input name="proactive_enabled" type="checkbox" defaultChecked={state.values.proactive_enabled} disabled={busy}/>{t("להציע זמן למשימות ולהזזת משבצות עבודה", "Suggest task time and work-block moves")}</label>
      <label>{t("כמה זמן להסתיר הצעה שבחרתי לדחות", "How long to hide a declined suggestion")}<select name="suggestion_snooze_minutes" defaultValue={state.values.suggestion_snooze_minutes} disabled={busy}><option value="60">{t("שעה", "One hour")}</option><option value="1440">{t("24 שעות", "24 hours")}</option></select></label>
      <label>{t("תזכורת כשאני פותח בקשת מעקב חדשה", "Follow-up when I start tracking an update")}<select name="request_followup_minutes" defaultValue={state.values.request_followup_minutes} disabled={busy}><option value="0">{t("רק כשאבחר בבקשה עצמה", "Only when I choose in the request")}</option><option value="60">{t("כעבור שעה", "After one hour")}</option><option value="1440">{t("כעבור 24 שעות", "After 24 hours")}</option></select></label>
      <label>{t("סגנון שאלות ההבהרה של העוזר", "Assistant clarification style")}<select name="reply_style" defaultValue={state.values.reply_style} disabled={busy}><option value="brief">{t("קצר וממוקד", "Brief and focused")}</option><option value="standard">{t("עם מעט יותר הסבר", "A little more explanation")}</option></select></label>
      <label>{t("מכסת התראות Push לכל מכשיר ביום", "Daily Push allowance per device")}<select name="push_daily_limit" defaultValue={state.values.push_daily_limit} disabled={busy}><option value="0">{t("ללא מכסה נוספת", "No additional limit")}</option>{[3,6,10].map(limit=><option key={limit} value={limit}>{limit}</option>)}</select></label>
      <p className="field-help">{t("המכסה נספרת לפי אזור הזמן שלך וכוללת הודעות שנעשו ניסיונות לשלוח. היא חלה גם על מטלות; יתר העדכונים נשארים בתיבה. שעות שקטות וסינון ההתראות ממשיכים לפעול. התראות דפדפן מקומיות אינן נספרות במכסת Push.", "The allowance follows your timezone and includes attempted notifications, including assignment reminders. Other updates stay in the inbox. Quiet hours and category filters still apply. Local browser notifications are separate from Push.")}</p>
      <label>{t("התראת השיעור הבא", "Next-class reminder")}<select name="class_reminder_minutes" defaultValue={state.values.class_reminder_minutes ?? 0} disabled={busy}><option value="0">{t("כבויה", "Off")}</option>{[10,15,30].map(minutes=><option key={minutes} value={minutes}>{t(`${minutes} דקות לפני השיעור`, `${minutes} minutes before class`)}</option>)}</select></label>
      <p className="field-help">{t("כוללת קורס, כיתה ומרצה כשהפרטים קיימים במקור. כפופה להרשאת Push, לשעות שקטות ולמכסה שבחרת. המחשב צריך לפעול.", "Includes course, room and lecturer when provided by the source. Requires Push permission and follows quiet hours and your allowance. Your computer must be running.")}</p>
      <Button type="submit" disabled={busy}>{t("שמירת העדפות המזכירה", "Save secretary preferences")}</Button>
    </form>}
    <p className="field-help">{t("חלונות ושעות עבודה נערכים בהעדפות התכנון שמתחת. שמירת שיחה מופעלת רק בבחירה מפורשת בעוזר, עם הכללים הקיימים של עד 30 יום ו־200 תורות.", "Edit work windows in Planning preferences below. Conversation storage requires opting in within the assistant, with the existing 30-day/200-turn limits.")}</p>
    <div className="google-actions"><Button size="small" variant="ghost" disabled={busy} onClick={()=>setReload(value=>value+1)}>{t("רענון ההעדפות", "Refresh preferences")}</Button><Button size="small" variant="ghost" onClick={()=>document.getElementById('lifeos-assistant-launcher')?.click()}>{t("הגדרות היסטוריית השיחה בעוזר", "Conversation history in assistant")}</Button></div>
    {message&&<p role="status">{message}</p>}
  </div>;
}
