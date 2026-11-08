import { dayKey, dueDay, shiftDay } from "./dates";
import type { AcademicItem, Course } from "./academic";

export type DeadlineStatus = "open" | "completed" | "all";
export type DeadlineKind = "assignment" | "exam" | "all";
export type DeadlinePeriod = "all" | "overdue" | "today" | "week";
export function academicOverdue(item:AcademicItem,now:Date,zone:string,today=dayKey(now,zone)) {
  return !item.completed && (item.due.length===10 ? item.due<today : Date.parse(item.due)<now.getTime());
}
export function academicDeadlines(items: AcademicItem[], courses: Course[], term: string, status: DeadlineStatus, kind: DeadlineKind, zone: string,period:DeadlinePeriod="all",now=new Date()) {
  const courseIds = new Set(courses.filter(course => term === "all" || course.term_id === term).map(course => course.id));
  const today=dayKey(now,zone),last=shiftDay(today,6);
  return items.filter(item => courseIds.has(item.course_id) && (status === "all" || item.completed === (status === "completed")) && (kind === "all" || item.kind === kind))
    .filter(item=>period!=="overdue" || academicOverdue(item,now,zone,today))
    .map(item=>({item,day:dueDay(item.due,zone),dateOnly:item.due.length===10,instant:item.due.length===10?0:Date.parse(item.due)}))
    .filter(({day})=>{
      if(period==="all"||period==="overdue")return true;
      return period==="today" ? day===today : day>=today&&day<=last;
    })
    .sort((a,b) => {
      const day = a.day.localeCompare(b.day);
      if (day) return day;
      return Number(a.dateOnly)-Number(b.dateOnly) || (!a.dateOnly && !b.dateOnly ? a.instant-b.instant : 0) || a.item.title.localeCompare(b.item.title) || a.item.id.localeCompare(b.item.id);
    })
    .map(value=>value.item);
}
