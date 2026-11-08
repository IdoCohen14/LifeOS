"use client";

import {useEffect,useState} from "react";
import {KeyRound,Download,Check,Copy} from "lucide-react";
import {api,ApiError} from "@/lib/api";
import type {Translate} from "@/lib/types";
import {Button} from "./ui/button";

export function AccountAccessSettings({csrf,t,onUnauthorized}:{csrf:string;t:Translate;onUnauthorized:()=>void}) {
  const [configured,setConfigured]=useState<boolean|null>(null);
  const [key,setKey]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  useEffect(()=>{let active=true;void api<{recovery_configured:boolean}>("accounts/access").then(value=>{if(active)setConfigured(value.recovery_configured);}).catch(()=>{if(active)setError(t("לא ניתן לבדוק את מפתח השחזור.","Could not check recovery key."));});return()=>{active=false;};},[csrf,t]);
  function download() {
    const url=URL.createObjectURL(new Blob(["LifeOS recovery key\n"+key+"\n"],{type:"text/plain;charset=utf-8"}));
    const anchor=document.createElement("a");anchor.href=url;anchor.download="LifeOS-recovery-key.txt";anchor.click();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  return <section className="panel account-access" aria-label={t("שחזור גישה לחשבון","Account access recovery")}>
    <h2><KeyRound size={20} aria-hidden="true"/> {t("מפתח שחזור אישי","Personal recovery key")}</h2>
    <p className="field-help">{t("אם שכחתם את הסיסמה, המפתח יאפשר לקבוע סיסמה חדשה. שמרו אותו במקום פרטי מחוץ ל־LifeOS. בלי הסיסמה והמפתח לא ניתן לשחזר גישה.","If you forget your password, this key lets you set a new one. Keep it private outside LifeOS. Without both your password and key, access cannot be recovered.")}</p>
    {key ? <div className="form-stack" role="region" aria-label={t("מפתח חד־פעמי להצגה","One-time key display")}>
      <p role="status">{t("זהו העותק היחיד שיוצג. מפתח קודם בוטל.","This is the only time the key is shown. Any previous key was replaced.")}</p>
      <label>{t("מפתח שחזור","Recovery key")}<textarea readOnly value={key} dir="ltr" autoComplete="off" spellCheck={false}/></label>
      <div className="button-row">
        <Button variant="secondary" onClick={()=>{void navigator.clipboard.writeText(key).catch(()=>setError(t("העתיקו את המפתח ידנית או הורידו קובץ.","Copy the key manually or download it.")));}}><Copy size={16}/>{t("העתקה","Copy")}</Button>
        <Button variant="secondary" onClick={download}><Download size={16}/>{t("הורדת המפתח","Download key")}</Button>
        <Button onClick={()=>{setKey("");setError("");}}><Check size={16}/>{t("שמרתי את המפתח","I saved the key")}</Button>
      </div>
    </div> : <form className="form-stack" onSubmit={async event=>{
      event.preventDefault();const form=event.currentTarget;const values=new FormData(form);
      setError("");setBusy(true);
      try{const result=await api<{recovery_key:string}>("accounts/access/key","POST",{password:values.get("password")},csrf);form.reset();setKey(result.recovery_key);setConfigured(true);}
      catch(error){if(error instanceof ApiError&&error.status===401)onUnauthorized();setError(t("המפתח לא נוצר. בדקו את הסיסמה והחיבור.","Could not create key. Check your password and connection."));}
      finally{setBusy(false);}
    }}>
      <label>{t("סיסמה נוכחית","Current password")}<input type="password" name="password" required minLength={8} maxLength={1024} autoComplete="current-password" dir="ltr" disabled={busy}/></label>
      {configured && <p className="field-help">{t("יצירת מפתח חדש תבטל את הקודם. שינוי סיסמה רגיל אינו מבטל את המפתח.","Creating a new key replaces the previous one. A normal password change keeps your key valid.")}</p>}
      <Button type="submit" disabled={busy||configured===null}>{configured?t("החלפת מפתח השחזור","Replace recovery key"):t("יצירת מפתח שחזור","Create recovery key")}</Button>
    </form>}
    {error&&<p className="error-message" role="alert">{error}</p>}
  </section>;
}

export function AccountAccessRecovery({t,onBack}:{t:Translate;onBack:()=>void}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[done,setDone]=useState(false);
  return <section className="form-stack" aria-label={t("שחזור גישה","Recover access")}>
    <h2>{t("שחזור באמצעות מפתח אישי","Recover with your personal key")}</h2>
    {!done ? <><p className="field-help">{t("הזינו את המפתח ששמרתם. הצלחה תנתק את כל המכשירים ותבטל את המפתח.","Enter your saved key. Success signs out all devices and consumes the key.")}</p>
      <form className="form-stack" onSubmit={async event=>{
        event.preventDefault();const form=event.currentTarget;const values=new FormData(form);setError("");
        if(values.get("password")!==values.get("confirm")){setError(t("הסיסמאות אינן תואמות.","Passwords do not match."));return;}
        setBusy(true);
        try{await api("accounts/access/recover","POST",{login:values.get("login"),recovery_key:values.get("key"),new_password:values.get("password")});form.reset();setDone(true);}
        catch{setError(t("הפרטים שגויים, המפתח אינו זמין או שנדרש להמתין לפני ניסיון נוסף.","Details are invalid, the key is unavailable, or you need to wait before retrying."));}
        finally{setBusy(false);}
      }}>
        <label>{t("שם משתמש","Username")}<input name="login" required maxLength={254} autoComplete="username" dir="ltr" disabled={busy}/></label>
        <label>{t("מפתח שחזור","Recovery key")}<input name="key" type="password" required maxLength={128} autoComplete="off" dir="ltr" disabled={busy}/></label>
        <label>{t("סיסמה חדשה","New password")}<input name="password" type="password" required minLength={8} maxLength={1024} autoComplete="new-password" dir="ltr" disabled={busy}/></label>
        <label>{t("אימות סיסמה חדשה","Confirm new password")}<input name="confirm" type="password" required minLength={8} maxLength={1024} autoComplete="new-password" dir="ltr" disabled={busy}/></label>
        <Button type="submit" disabled={busy}>{t("איפוס הסיסמה","Reset password")}</Button>
      </form></> : <p role="status">{t("הסיסמה שונתה. היכנסו לחשבון וצרו מפתח שחזור חדש בהגדרות.","Password changed. Sign in, then create a new recovery key in settings.")}</p>}
    {error&&<p role="alert" className="error-message">{error}</p>}
    <Button variant="secondary" disabled={busy} onClick={onBack}>{t("חזרה לכניסה","Back to sign in")}</Button>
  </section>;
}
