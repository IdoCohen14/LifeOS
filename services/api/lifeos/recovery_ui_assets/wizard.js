"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const capability = location.hash.slice(1);
  history.replaceState(null, "", location.pathname);
  let language = "he", state = null, preview = null, busy = false, done = false;
  const hebrew = new Map([...document.querySelectorAll("[data-copy]")].map(node => [node.dataset.copy,node.textContent]));
  const english = {
    theme:"Theme",system:"System",dark:"Dark",light:"Light",title:"Return to a saved point",
    intro:"Choose a backup, review it, then confirm restoration. The main LifeOS app must be closed.",
    target:"Data folder to replace",selectStep:"Choose",reviewStep:"Review",doneStep:"Complete",
    selectTitle:"Which backup should return?",savedOnly:"Choose a saved backup or an encrypted file from another folder. The file is sent only to this local recovery helper, without an external service.",
    sourceChoice:"Backup source",savedSource:"Backup saved in the app",fileSource:"Choose a file from another folder",fileLabel:"Encrypted backup file",sourceName:"Inspected source file",
    backupLabel:"Saved backup",password:"Backup password",inspect:"Check backup",noChange:"Checking does not replace data. The password clears after each attempt.",
    reviewTitle:"Review before replacing",snapshot:"Snapshot created",tasks:"Tasks",events:"Personal events",
    consequence:"Restoring replaces your data and login password with those from the backup. An encrypted safety backup of the current state is created first, using this same backup password. Sessions reset; Push and automatic backup stay off.",
    expire:"This review is valid for10minutes. Changed files require a new review.",repeatPassword:"Enter backup password again to confirm",
    consent:"I reviewed the backup and target folder, and approve replacing the current data",restore:"Confirm and restore data",back:"Choose another backup",
    completeTitle:"Restore complete",completeText:"Close the recovery window and start LifeOS again. Sign in using the app password that was active when this backup was created.",
    reconnect:"Google or Moodle may need reconnecting on another Windows profile or computer.",footer:"Everything stays on this computer. Recovery does not upload data to an external service."
  };
  const t = (he,en) => language === "he" ? he : en;
  function step(value) {
    ["selection","review","complete"].forEach((id,index) => {
      $(id).hidden = index !== value;
      $("step"+(index+1)).toggleAttribute("aria-current",index === value);
      if(index === value) $("step"+(index+1)).setAttribute("aria-current","step");
    });
  }
  function localDate(value) { return new Intl.DateTimeFormat(language,{dateStyle:"medium",timeStyle:"short",timeZone:"Asia/Jerusalem"}).format(new Date(value)); }
  function render() {
    document.documentElement.lang=language;
    document.documentElement.dir=language==="he"?"rtl":"ltr";
    document.title=language==="he"?"LifeOS · שחזור":"LifeOS · Recovery";
    document.querySelector(".steps").setAttribute("aria-label",t("שלבי שחזור","Recovery steps"));
    document.querySelectorAll("[data-copy]").forEach(node=>{node.textContent=language==="he"?hebrew.get(node.dataset.copy):english[node.dataset.copy];});
    $("language").textContent=language==="he"?"English":"עברית";
    if(state) {
      $("fixture").hidden=!state.test_mode;
      $("fixture").textContent=t("מצב בדיקה — נתוני דוגמה בלבד","Test mode — synthetic data only");
      const selected=$("backup").value;
      $("directory").textContent=state.directory;
      $("backup").replaceChildren(...state.backups.map(row=>{
        const option=document.createElement("option");option.value=row.id;
        option.textContent=`${localDate(row.created_at)} · ${(row.size/1048576).toFixed(2)} MiB`;
        return option;
      }));
      if(state.backups.some(row=>row.id===selected)) $("backup").value=selected;
      if(!state.backups.length) $("status").textContent=t("אין גיבויים מוצפנים שמורים בתיקייה הזאת.","No encrypted backups saved in this folder.");
    }
    sourceState();
    if(preview) {
      $("source-name").textContent=preview.source_name || preview.backup_id;
      $("snapshot").textContent=localDate(preview.created_at);
      $("tasks").textContent=String(preview.counts.tasks);
      $("events").textContent=String(preview.counts.events);
    }
  }
  function sourceState() {
    const file=$("source-kind").value==="file";
    $("saved-source").hidden=file;$("file-source").hidden=!file;
    $("backup").disabled=file;$("backup").required=!file;
    $("backup-file").disabled=!file;$("backup-file").required=file;
  }
  function working(value) {
    busy=value;
    document.querySelectorAll("fieldset").forEach(node=>{node.disabled=value;});
    $("inspect-form").querySelector("fieldset").disabled=value || !state || done;
    sourceState();
    $("inspect-submit").disabled=value || !state || done || ($("source-kind").value==="file"?!$("backup-file").files.length:!state.backups.length);
    $("restore").disabled=value || !$("confirm").checked || done;
    $("status").textContent=value?t("מעבד…","Processing…"):"";
  }
  function error(code) {
    const message=code === "close_lifeos_before_recovery" ? t("יש לסגור את LifeOS ואת חלון ההפעלה שלו לפני שחזור, ואז לנסות שוב.","Close LifeOS and its launcher before restoring, then retry.")
      : code === "recovery_session_expired" ? t("חלון השחזור פג תוקף. סגרו את כלי השחזור ופתחו אותו מחדש.","The recovery session expired. Close the recovery launcher and reopen it.")
      : code === "recovery_retry_later" ? t("היו כמה ניסיונות שלא הצליחו. המתינו דקה ונסו שוב.","Several attempts failed. Wait a minute and retry.")
      : ["backup_changed","recovery_preview_expired"].includes(code) ? t("הגיבוי או הבדיקה השתנו. חזרו לבחירה ובדקו מחדש לפני אישור.","The backup or review changed. Go back and check it again before confirming.")
      : code === "backup_too_large" ? t("קובץ הגיבוי גדול מהמגבלה המותרת. הנתונים הנוכחיים לא הוחלפו.","The backup file exceeds the allowed size. Current data was not replaced.")
      : code === "backup_invalid" ? t("לא ניתן לאמת את הגיבוי. בדקו את סיסמת הגיבוי ואת תקינות הקובץ.","Could not validate the backup. Check its backup password and file integrity.")
      : t("הפעולה לא הושלמה. אפשר לנסות שוב; אם אירעה הפרעה לשחזור, השתמשו בכלי השחזור המקומי.","The operation did not complete. Retry; if recovery was interrupted, use the local recovery tool.");
    $("error").textContent=message;$("error").hidden=false;$("error").focus();
  }
  function clearError() { $("error").hidden=true;$("error").textContent=""; }
  async function api(path,data) {
    const response=await fetch(`/api/${path}`,{method:data?"POST":"GET",cache:"no-store",headers:{"X-Recovery-Token":capability,...(data?{"Content-Type":"application/json"}:{})},...(data?{body:JSON.stringify(data)}:{})});
    const result=await response.json();
    if(!response.ok) throw new Error(result.detail||"unavailable");
    return result;
  }
  async function uploadBackup(file) {
    if(!file || !state || file.size>state.max_upload_bytes) throw new Error("backup_too_large");
    const response=await fetch("/api/upload",{method:"POST",cache:"no-store",headers:{"X-Recovery-Token":capability,"Content-Type":"application/octet-stream","X-Backup-Name":encodeURIComponent(file.name)},body:file});
    const result=await response.json();
    if(!response.ok) throw new Error(result.detail||"unavailable");
    return result;
  }
  $("source-kind").addEventListener("change",()=>{if(!busy){sourceState();working(false);}});
  $("backup-file").addEventListener("change",()=>{if(!busy)working(false);});
  $("language").addEventListener("click",()=>{language=language==="he"?"en":"he";render();});
  $("theme").addEventListener("change",()=>{const value=$("theme").value;if(value==="system")document.documentElement.removeAttribute("data-theme");else document.documentElement.dataset.theme=value;});
  $("inspect-form").addEventListener("submit",async event=>{
    event.preventDefault();if(busy)return;clearError();working(true);preview=null;
    const password=$("inspect-password").value;$("inspect-password").value="";
    try {
      let backupId=$("backup").value;
      if($("source-kind").value==="file") backupId=(await uploadBackup($("backup-file").files[0])).id;
      preview=await api("inspect",{backup_id:backupId,password});render();step(1);$("review-heading").focus();
    }
    catch(failure){error(failure.message);}
    finally{working(false);}
  });
  $("confirm").addEventListener("change",()=>{$("restore").disabled=!$("confirm").checked||busy||done;});
  $("back").addEventListener("click",()=>{if(busy)return;preview=null;$("restore-password").value="";$("confirm").checked=false;clearError();step(0);$("source-kind").focus();});
  $("restore-form").addEventListener("submit",async event=>{
    event.preventDefault();if(busy||done||!preview||!$("confirm").checked)return;clearError();working(true);
    const password=$("restore-password").value;$("restore-password").value="";
    try { const result=await api("restore",{id:preview.id,password,confirm:true});done=true;step(2);$("safety").textContent=result.safety_backup_id?t("גיבוי הבטיחות נשמר בתיקיית הגיבויים.","The safety backup was saved in the backups folder."):"";$("complete-heading").focus(); }
    catch(failure){error(failure.message);}
    finally{working(false);}
  });
  window.addEventListener("beforeunload",event=>{if(busy){event.preventDefault();event.returnValue="";}});
  render();
  if(!capability) {error("recovery_session_expired");return;}
  working(true);
  api("state").then(result=>{state=result;done=state.completed;if(!state.backups.length)$("source-kind").value="file";render();if(done)step(2);}).catch(failure=>error(failure.message)).finally(()=>working(false));
})();
