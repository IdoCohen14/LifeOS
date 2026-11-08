"use client";
import { useId } from "react";
import { Check, GraduationCap } from "lucide-react";
import type { Translate } from "@/lib/types";
import { Button } from "./ui/button";

export function AcademicStartGuide({hasTerm,hasCourse,hasItem,disabled=false,t,onTerm,onCourse,onItem,onSession}:{
 hasTerm:boolean;hasCourse:boolean;hasItem:boolean;disabled?:boolean;t:Translate;onTerm:()=>void;onCourse:()=>void;onItem:()=>void;onSession:()=>void;
}) {
 const heading=useId(),count=Number(hasTerm)+Number(hasCourse)+Number(hasItem);
 const steps=[
  {done:hasTerm,title:t("סמסטר","Term"),help:t("תאריכי התחלה וסיום שמרכזים את הקורסים.","Start and end dates that group your courses."),label:t("הוספת סמסטר","Add a term"),action:onTerm,enabled:true},
  {done:hasCourse,title:t("קורסים","Courses"),help:t("הקורסים בסמסטר שבחרת, עם הפרטים שחשובים לך.","Courses in the selected term, with the details you need."),label:t("הוספת קורס","Add a course"),action:onCourse,enabled:hasTerm},
  {done:hasItem,title:t("מטלה או מבחן ראשון","First assignment or exam"),help:t("שמרו מועד אמיתי. אחר כך אפשר להקצות לו זמן ביומן.","Save a real deadline. You can then allocate time in the calendar."),label:t("הוספת מטלה ראשונה","Add your first assignment"),action:onItem,enabled:hasCourse},
 ];
 return <section className="panel academic-start" aria-labelledby={heading}><details open={count<3}>
  <summary><div className="heading-with-icon"><GraduationCap size={22} aria-hidden="true"/><h2 id={heading}>{t("מתחילים לנהל את הלימודים","Start managing your studies")}</h2></div><span className="subtle-badge">{t(`${count}/3 הוגדרו`,`${count}/3 configured`)}</span></summary>
  <div className="academic-start-body">
   <p className="field-help">{t("ההתקדמות מתייחסת לסוגי מידע שהזנת בסמסטר שבחרת, לא להשלמת הלימודים. הקורסים והמטלות כאן מנוהלים ידנית.","Progress counts configured record types in the selected term, not study completion. Courses and assignments here are managed manually.")}</p>
   <progress max={3} value={count} aria-label={t("התקדמות בהגדרת הלימודים","Academic setup progress")}/>
   <ol className="academic-start-steps">{steps.map((step,index)=><li key={index}>
    <span className={`setup-step-marker${step.done?" is-ready":""}`} aria-hidden="true">{step.done?<Check size={15}/>:index+1}</span>
    <div><strong>{step.title}</strong><p className="field-help">{step.help}</p><Button variant="secondary" disabled={disabled||!step.enabled} onClick={step.action}>{step.label}</Button></div>
   </li>)}</ol>
   <div className="academic-start-optional"><p className="field-help">{t("מערכת שעות שבועית היא אופציונלית. הוסיפו אותה כשיש שעות לימוד קבועות.","A weekly timetable is optional. Add it when you have fixed class times.")}</p><Button variant="ghost" disabled={disabled||!hasCourse} onClick={onSession}>{t("הוספת מפגש שבועי אופציונלי","Add an optional weekly session")}</Button></div>
  </div>
 </details></section>;
}
