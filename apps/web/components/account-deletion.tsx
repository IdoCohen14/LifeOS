"use client";

import {useState} from "react";
import {Trash2,ShieldAlert} from "lucide-react";
import {api} from "@/lib/api";
import type {Translate} from "@/lib/types";
import {Button} from "./ui/button";

type Review={id:string;login:string;counts:Record<string,number>;expires:number};
export function AccountDeletionSettings({csrf,t,onDeleted=()=>window.location.reload()}:{csrf:string;t:Translate;onDeleted?:()=>void}) {
  const [review,setReview]=useState<Review|null>(null),[busy,setBusy]=useState(false);
  const [login,setLogin]=useState(""),[password,setPassword]=useState("");
  const [error,setError]=useState(""),[pending,setPending]=useState(false);
  const groups: [string,string,string][]=[['tasks','משימות','Tasks'],['events','אירועים אישיים','Personal events'],['courses','קורסים','Courses'],['documents','מסמכים','Documents'],['account_providers','חיבורים','Connections']];
  return <section className="panel account-deletion" aria-label={t("מחיקת חשבון","Account deletion")}>
    <h2><ShieldAlert size={20} aria-hidden="true"/> {t("מחיקת חשבון","Delete account")}</h2>
    <p className="field-help">{t("מחיקה מסירה את המידע והגיבויים המנוהלים של החשבון הזה מ־LifeOS. אפשר לייצא גיבוי בסעיף גיבוי החשבון לפני שממשיכים.","Deletion removes this account's data and managed backups from LifeOS. You can export a backup in Account backup before continuing.")}</p>
    <p className="field-help">{t("מיילים ואירועים ב־Google אינם נמחקים. קבצים שכבר הורדתם ועותקי גיבוי נפרדים של השרת אינם נמחקים כאן.","Emails and events at Google are not deleted. Previously downloaded files and separate server backup copies are not deleted here.")}</p>
    {pending ? <><p role="status">{t("החשבון נחסם. ניקוי הארכיונים עדיין דורש טיפול מפעיל; המחיקה טרם הושלמה.","Your account is disabled. Archive cleanup still needs operator attention; deletion is not complete.")}</p><Button variant="secondary" onClick={()=>window.location.reload()}>{t("חזרה לכניסה","Back to sign in")}</Button></> : !review ? <Button variant="danger" disabled={busy} onClick={async()=>{
      setBusy(true);setError("");try{setReview(await api<Review>("accounts/deletion/preview","POST",{},csrf));}
      catch{setError(t("לא ניתן להכין סקירה. בדקו את החיבור והיכנסו שוב אם צריך.","Could not prepare a review. Check your connection and sign in again if needed."));}
      finally{setBusy(false);}
    }}><Trash2 size={16}/>{t("סקירת מחיקת החשבון","Review account deletion")}</Button> : <div className="form-stack">
      <p>{t("החשבון שיימחק:","Account to delete:")} <bdi>{review.login}</bdi></p>
      <ul className="muted">{groups.filter(([key])=>review.counts[key]).map(([key,he,en])=><li key={key}>{t(he,en)}: {review.counts[key]}</li>)}</ul>
      <p>{t("כל המידע בחשבון יימחק, כולל הגדרות, היסטוריה, מידע לימודי, חיבורים והתחברויות. הפעולה אינה ניתנת לביטול דרך האתר. הסקירה תקפה לעשר דקות.","All account data will be removed, including settings, history, academic data, connections and sessions. This cannot be undone through the site. The review is valid for ten minutes.")}</p>
      <form className="form-stack" onSubmit={async event=>{
        event.preventDefault();if(login!==review.login||!password||busy)return;
        setBusy(true);setError("");
        try{const result=await api<{deleted:boolean;cleanup_pending:boolean}>("accounts/deletion/confirm","POST",{preview_id:review.id,login,password},csrf);setPassword("");
          if(result.deleted)onDeleted();else if(result.cleanup_pending){setPending(true);setReview(null);}
          else setError(t("המחיקה לא הושלמה.","Deletion did not complete."));
        }catch{setPassword("");setError(t("המחיקה לא הושלמה. בדקו את הסיסמה ושם המשתמש; אם הסקירה פגה, פתחו סקירה חדשה.","Deletion did not complete. Check your password and username; if the review expired, create a new review."));}
        finally{setBusy(false);}
      }}>
        <label>{t("הקלידו את שם המשתמש","Type your username")}<input value={login} onChange={event=>setLogin(event.target.value)} required maxLength={254} autoComplete="off" dir="ltr" disabled={busy}/></label>
        <label>{t("סיסמה נוכחית","Current password")}<input value={password} onChange={event=>setPassword(event.target.value)} type="password" required minLength={8} maxLength={1024} autoComplete="current-password" dir="ltr" disabled={busy}/></label>
        <div className="button-row"><Button type="submit" variant="danger" disabled={busy||login!==review.login||password.length<8}>{t("מחיקת חשבון LifeOS שלי","Delete my LifeOS account")}</Button>
          <Button variant="secondary" disabled={busy} onClick={()=>{setReview(null);setPassword("");setLogin("");setError("");}}>{t("ביטול","Cancel")}</Button></div>
      </form>
    </div>}
    {error&&<p role="alert" className="error-message">{error}</p>}
  </section>;
}
