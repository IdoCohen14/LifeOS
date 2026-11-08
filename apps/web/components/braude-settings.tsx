"use client";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";
import type { MoodleStatus } from "./moodle-settings";

export function BraudeSettings({csrf,t,settings,onChanged,onUnauthorized}:{csrf:string;t:Translate;settings:Settings;onChanged:()=>Promise<void>;onUnauthorized:()=>void}) {
  const [status,setStatus]=useState<MoodleStatus|null>(null);
  const [url,setUrl]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState(false);
  const [notice,setNotice]=useState("");
  const [disconnecting,setDisconnecting]=useState(false);
  useEffect(()=>{
    let active=true;
    const load=()=>api<MoodleStatus>("integrations/braude/status").then(s=>{if(active){setStatus(s);setError(false);}}).catch(e=>{
      if(active){setError(true);if(e instanceof ApiError&&e.status===401)onUnauthorized();}
    });
    void load();
    const timer=setInterval(()=>void load(),10000);
    return()=>{active=false;clearInterval(timer);};
  },[csrf,onUnauthorized]);
  async function act(path:string,body?:unknown) {
    setBusy(true);setError(false);setNotice("");
    try {
      await api(`integrations/braude/${path}`,"POST",body,csrf);
      setUrl("");
      if(path==="config")await api("integrations/braude/sync?background=true","POST",undefined,csrf);
      if(path==="config"||path.startsWith("sync"))setNotice(t("בקשת הסנכרון נשלחה. הנתונים יתעדכנו לאחר סנכרון מוצלח.","Sync requested. Data will refresh after a successful sync."));
      setStatus(await api<MoodleStatus>("integrations/braude/status"));
      await onChanged();
      return true;
    } catch(e) {setError(true);if(e instanceof ApiError&&e.status===401)onUnauthorized();return false;} finally {setBusy(false);}
  }
  return <section className="google-settings">
    <h3>{t("תחנת המידע · בראודה","Braude student portal")}</h3>
    <p>{t("יומן אישי מתעדכן לקריאה בלבד. הקישור נשמר מוצפן; אין צורך בסיסמת המכללה.","Read-only personal calendar subscription. The link is encrypted; no college password needed.")}</p>
    {status&&!status.configured&&<form onSubmit={e=>{e.preventDefault();void act("config",{url});}}>
      <label>{t("קישור היומן מתחנת המידע","Student portal calendar link")}<input type="password" dir="ltr" autoComplete="off" spellCheck={false} maxLength={8192} value={url} onChange={e=>setUrl(e.target.value)} required/></label>
      <Button disabled={busy} type="submit">{t("חיבור תחנת המידע","Connect student portal")}</Button>
    </form>}
    {status?.configured&&<><p role="status">{status.last_success?t(`${status.event_count} אירועים נשמרו בסנכרון האחרון.`,`${status.event_count} events saved at the last sync.`):t("ממתין לסנכרון מוצלח","Waiting for a successful sync")}</p>
      {status.last_success&&<p className="field-help">{t("סנכרון אחרון: ","Last synced: ")}{new Intl.DateTimeFormat(settings.language,{dateStyle:"short",timeStyle:"short",timeZone:settings.timezone}).format(new Date(status.last_success*1000))}</p>}
      <div className="google-actions"><Button disabled={busy||status.syncing} onClick={()=>void act("sync?background=true")}>{status.syncing?t("מסנכרן…","Syncing…"):t("סנכרון עכשיו","Sync now")}</Button>
        <Button variant="ghost" disabled={busy||status.syncing} onClick={()=>setDisconnecting(true)}>{t("ניתוק תחנת המידע","Disconnect student portal")}</Button></div></>}
    <p className="field-help">{t("מתעדכן בערך כל 10 דקות כשהמחשב פועל. מיובאים האירועים שהמקור מפרסם; אין הסקה של קורסים או מבחנים שאינם מופיעים בו.","Updates about every 10 minutes while the PC runs. Imports only events published by the source; missing courses or exams are not inferred.")}</p>
    {(error||status?.error||status?.stale)&&<p role="alert">{t("הסנכרון לא הושלם או אינו מעודכן. מידע קודם נשמר עד עדכון מוצלח.","Sync failed or is outdated. Previous data is retained until a successful update.")}</p>}
    {notice&&<p role="status">{notice}</p>}
    <Modal open={disconnecting} onClose={()=>setDisconnecting(false)} title={t("ניתוק תחנת המידע?","Disconnect student portal?")} description={t("הסרה מקומית בלבד","Local removal only")} closeLabel={t("סגירה","Close")}>
      <p>{t("קישור המנוי ואירועי מערכת השעות המיובאים יוסרו מ־LifeOS והסנכרון ייפסק. הקורסים, המטלות והמבחנים שכבר נקלטו יישארו. לא ישתנה מידע במכללה.","Removes the subscription and imported timetable events from LifeOS and stops syncing. Existing courses, assignments and exams remain. Nothing changes at your institution.")}</p>
      <Button variant="danger" disabled={busy} onClick={async()=>{if(await act("disconnect"))setDisconnecting(false);}}>{t("אישור ניתוק","Confirm disconnection")}</Button>
    </Modal>
  </section>;
}
