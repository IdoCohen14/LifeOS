"use client";
import { useId, useMemo } from "react";
import { CalendarDays } from "lucide-react";
import type { Course, Slot, Term } from "@/lib/academic";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";

export function AcademicTimetable({slots,courses,terms,term,settings,t,onSelect}:{
  slots:Slot[];courses:Course[];terms:Term[];term:string;settings:Settings;t:Translate;onSelect:(id:string)=>void;
}) {
  const heading=useId();
  const courseMap=useMemo(()=>new Map(courses.filter(course=>term==="all"||course.term_id===term).map(course=>[course.id,course])),[courses,term]);
  const selected=useMemo(()=>slots.filter(slot=>courseMap.has(slot.course_id)).sort((a,b)=>a.weekday-b.weekday||a.start_time.localeCompare(b.start_time)||a.end_time.localeCompare(b.end_time)||a.id.localeCompare(b.id)),[slots,courseMap]);
  const termMap=useMemo(()=>new Map(terms.map(term=>[term.id,term.name])),[terms]);
  return <section className="panel academic-weekly" aria-labelledby={heading}><details>
    <summary><div className="heading-with-icon"><CalendarDays size={22} aria-hidden="true"/><h2 id={heading}>{t("מערכת שעות שבועית","Weekly timetable")}</h2></div><span className="subtle-badge">{t(`${selected.length} מפגשים`,`${selected.length} sessions`)}</span></summary>
    <p className="field-help weekly-note">{t("המערכת הידנית של הקורסים התואמים לסמסטר ולחיפוש. שעות כל מפגש לפי אזור הזמן שמופיע לידו; ביטולים וחגים אינם מוסקים אוטומטית.","The manual weekly template for courses matching the term and search. Each session uses its displayed timezone; cancellations and holidays are not inferred.")}</p>
    {selected.length ? Array.from({length:7},(_,weekday)=>{
      const list=selected.filter(slot=>slot.weekday===weekday);
      if(!list.length)return null;
      const name=new Intl.DateTimeFormat(settings.language,{weekday:"long",timeZone:"UTC"}).format(new Date(Date.UTC(2026,9,25+weekday)));
      return <section className="weekly-day" key={weekday} aria-labelledby={`${heading}-${weekday}`}>
        <h3 id={`${heading}-${weekday}`}>{name}</h3><ul className="academic-list">{list.map(slot=>{
          const course=courseMap.get(slot.course_id)!;
          return <li key={slot.id}><div className="academic-record-content">
            <strong><bdi>{slot.start_time}–{slot.end_time}</bdi></strong>
            <Button className="deadline-course" variant="ghost" aria-label={`${t("פתיחת מערכת הקורס","Open course timetable")}: ${course.name}`} onClick={()=>onSelect(course.id)}><span dir="auto">{course.name}</span></Button>
            <p className="record-meta"><span dir="auto">{slot.location||t("ללא מיקום","No location")}</span><bdi>{slot.timezone}</bdi><span dir="auto">{termMap.get(course.term_id)}</span></p>
          </div></li>;
        })}</ul>
      </section>;
    }):<p className="deadline-empty" role="status">{t("אין מפגשים שבועיים בסמסטר שנבחר. אפשר להוסיף מפגש או לשנות סינון סמסטר.","No weekly sessions in the selected term. Add a session or change the term filter.")}</p>}
  </details></section>;
}
