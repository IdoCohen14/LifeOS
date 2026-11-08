import { eventOnDay, localInput } from "./dates";
import type { CalendarEvent } from "./types";

export function classRoom(event: CalendarEvent) {
  const raw = event.notes.match(/(?:^|\n)חדר:\s*([^\n]+)/)?.[1]?.trim()
    ?? (event.source === "timetable" ? event.notes.trim() : "");
  if (!raw) return null;
  const buildingFirst = raw.match(/\b([A-Za-z])\s*[-/]?\s*(\d{3})\b/);
  if (buildingFirst) return `${buildingFirst[1].toUpperCase()} ${buildingFirst[2]}`;
  const roomFirst = raw.match(/\b(\d{3})\s*[-/]?\s*([A-Za-z])\b/);
  if (roomFirst) return `${roomFirst[2].toUpperCase()} ${roomFirst[1]}`;
  return raw; // Preserve a genuine source location such as an online classroom.
}

export function isClassEvent(event: CalendarEvent) {
  if (event.source === "timetable") return true;
  if (event.source !== "braude" || event.all_day) return false;
  const text = `${event.title} ${event.notes}`;
  if (/(?:בחינה|בחינות|מבחן|מבחנים|מועד\s+[אבג]|exam|examination)/i.test(text)) return false;
  // Only explicit teaching-session markers from the official source. Unknown
  // portal events remain visible in the main calendar rather than disappearing.
  return /(?:הרצאה|תרגיל|תרגול|מעבדה)/.test(event.notes);
}

export function dayClassLayout(events: CalendarEvent[], day: string, zone: string) {
  const minute = (value: string) => Number(value.slice(11,13))*60+Number(value.slice(14,16));
  const rows = events.filter(e=>isClassEvent(e)&&!e.all_day&&eventOnDay(e,day,zone)).map(event=>{
    const start=localInput(event.start,zone),end=localInput(event.end,zone);
    return {event,start:start.slice(0,10)<day?0:minute(start),end:end.slice(0,10)>day?1440:minute(end),lane:0};
  }).sort((a,b)=>a.start-b.start||a.end-b.end||a.event.id.localeCompare(b.event.id));
  const ends:number[]=[];
  for(const row of rows){let lane=ends.findIndex(end=>end<=row.start);if(lane<0)lane=ends.length;row.lane=lane;ends[lane]=row.end;}
  return {rows,lanes:Math.max(1,ends.length)};
}
