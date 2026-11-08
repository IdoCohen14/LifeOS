"use client";
import { useState } from "react";
import { classRoom, dayClassLayout } from "@/lib/class-schedule";
import { formatDay, formatTime, shiftDay, weekDays } from "@/lib/dates";
import type { CalendarEvent, Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";
import type { Course } from "@/lib/academic";

export function ClassTimetable({events,today,initialDay,settings,t,courses=[]}:{events:CalendarEvent[];today:string;initialDay?:string|null;settings:Settings;t:Translate;courses?:Course[]}) {
  const [day,setDay]=useState(initialDay || today);
  const [mode,setMode]=useState<"day"|"week">("day");
  const [selected,setSelected]=useState<CalendarEvent|null>(null);
  const days=weekDays(day);
  const layouts=days.map(day=>dayClassLayout(events,day,settings.timezone));
  const rows=layouts.flatMap(day=>day.rows);
  const dayRows=dayClassLayout(events,day,settings.timezone).rows;
  const lecturer=(event:CalendarEvent)=>courses.find(course=>course.id===event.course_id)?.instructor || t("מרצה לא צוין במידע הזמין", "Lecturer not in available data");
  const first=Math.min(480,...rows.map(r=>Math.floor(r.start/60)*60));
  const last=Math.max(1080,...rows.map(r=>Math.ceil(r.end/60)*60));
  const scale=1.5;
  return <section className="class-schedule" aria-label={t("מערכת שעות לפי שעות השיעורים","Timetable by class times")}>
    <div className="calendar-toolbar">
      <Button variant="secondary" onClick={()=>setDay(today)}>{t("היום","Today")}</Button>
      <Button variant="ghost" onClick={()=>setDay(shiftDay(day,mode==="day"?-1:-7))}>{mode==="day"?t("יום קודם","Previous day"):t("שבוע קודם","Previous week")}</Button>
      <strong>{mode==="day"?formatDay(day,settings.language,{weekday:"long",day:"numeric",month:"short"}):`${formatDay(days[0],settings.language,{day:"numeric",month:"short"})} – ${formatDay(days[6],settings.language,{day:"numeric",month:"short"})}`}</strong>
      <Button variant="ghost" onClick={()=>setDay(shiftDay(day,mode==="day"?1:7))}>{mode==="day"?t("יום הבא","Next day"):t("שבוע הבא","Next week")}</Button>
      <div className="segmented" role="group" aria-label={t("תצוגת מערכת שעות","Timetable view")}><button type="button" aria-pressed={mode==="day"} onClick={()=>setMode("day")}>{t("יום","Day")}</button><button type="button" aria-pressed={mode==="week"} onClick={()=>setMode("week")}>{t("שבוע","Week")}</button></div>
    </div>
    <nav className="class-mobile-days" aria-label={t("יום במערכת השעות", "Timetable day")}>
      {days.map(date=><button type="button" key={date} aria-pressed={date===day} onClick={()=>setDay(date)}>
        <span>{formatDay(date,settings.language,{weekday:"short"})}</span><strong>{Number(date.slice(-2))}</strong>
        <i aria-hidden="true" className={dayClassLayout(events,date,settings.timezone).rows.length?"has-classes":""}/>
      </button>)}
    </nav>
    {mode==="day"&&<div className="calm-day-lessons">{dayRows.length?dayRows.map(row=><article className="calm-lesson" key={row.event.id}><div className="calm-lesson-time"><time dateTime={row.event.start}>{formatTime(row.event.start,settings.language,settings.timezone)}</time><time dateTime={row.event.end}>{formatTime(row.event.end,settings.language,settings.timezone)}</time></div><button type="button" className="calm-lesson-body" onClick={()=>setSelected(row.event)}><strong dir="auto">{row.event.title}</strong><span>{t("בניין וחדר", "Building and room")}: <bdi>{classRoom(row.event)??t("לא צוין במקור", "Not provided by source")}</bdi></span><span dir="auto">{lecturer(row.event)}</span></button></article>):<p role="status" className="field-help">{t("אין שיעורים במידע השמור ליום הזה.","No classes in the saved data for this day.")}</p>}</div>}
    <div hidden={mode!=="week"} className="calm-week-timetable">
    <div className="class-schedule-scroll" tabIndex={0} aria-label={t("טבלת שעות שבועית נגללת","Scrollable weekly timetable")}>
      <div className="class-schedule-grid">
        <div className="class-axis-heading">{t("שעה","Time")}</div>
        {days.map(date=><div className={`class-day-heading ${date===today?"is-today":""} ${date===day?"mobile-selected":""}`} key={date}><strong>{formatDay(date,settings.language,{weekday:"long"})}</strong><span>{formatDay(date,settings.language,{day:"numeric",month:"short"})}</span></div>)}
        <div className="class-time-axis" style={{height:(last-first)*scale}}>{Array.from({length:(last-first)/60+1},(_,i)=><span key={i} style={{top:i*60*scale}}><bdi>{String(first/60+i).padStart(2,"0")}:00</bdi></span>)}</div>
        {layouts.map((layout,index)=><div className={`class-day-column ${days[index]===day?"mobile-selected":""}`} key={days[index]} style={{height:(last-first)*scale}}>
          {Array.from({length:(last-first)/60},(_,i)=><div key={i} className="class-hour-line" style={{top:i*60*scale}}/>)}
          {layout.rows.map(row=><button key={row.event.id} className="class-time-block" onClick={()=>setSelected(row.event)} style={{top:(row.start-first)*scale,height:(row.end-row.start)*scale,insetInlineStart:`${row.lane*100/layout.lanes}%`,width:`calc(${100/layout.lanes}% - 5px)`}}><bdi>{formatTime(row.event.start,settings.language,settings.timezone)}–{formatTime(row.event.end,settings.language,settings.timezone)}</bdi><span className="class-room" title={t("בניין וחדר", "Building and room")}><bdi dir="ltr">{classRoom(row.event)??t("חדר לא צוין", "Room not specified")}</bdi></span><strong dir="auto">{row.event.title}</strong></button>)}
        </div>)}
      </div>
    </div>
    {!rows.length&&<p role="status">{t("אין שיעורים מסונכרנים בשבוע הזה.","No synced classes this week.")}</p>}
    </div>
    <Modal open={!!selected} onClose={()=>setSelected(null)} title={selected?.title??""} description={t("פרטי השיעור מהמקור","Source class details")} closeLabel={t("סגירה","Close")}>
      {selected&&<><p className="class-room">{t("בניין וחדר: ","Building and room: ")}<bdi dir="ltr">{classRoom(selected)??t("לא צוין במקור","Not provided by source")}</bdi></p><p><bdi>{formatTime(selected.start,settings.language,settings.timezone)}–{formatTime(selected.end,settings.language,settings.timezone)}</bdi></p><p dir="auto">{lecturer(selected)}</p><p dir="auto">{selected.notes}</p>{selected.source_url&&<a href={selected.source_url} target="_blank" rel="noreferrer">{t("פתיחת מקור המידע","Open source")}</a>}</>}
    </Modal>
  </section>;
}
