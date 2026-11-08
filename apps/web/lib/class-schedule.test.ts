import { describe,expect,it } from "vitest";
import { classRoom,dayClassLayout,isClassEvent } from "./class-schedule";
import type { CalendarEvent } from "./types";
const event:CalendarEvent={id:"fixture",title:"Fixture course",notes:"הרצאה",source:"braude",all_day:false,start:"2026-11-01T06:30:00Z",end:"2026-11-01T08:00:00Z",created_at:"2026-01-01T00:00:00Z"};
describe("class schedule",()=>{
 it("clips an overnight class to each local day and excludes its exclusive end",()=>{
   const overnight={...event,start:"2026-11-03T22:00:00+02:00",end:"2026-11-04T02:00:00+02:00"};
   expect(dayClassLayout([overnight],"2026-11-03","Asia/Jerusalem").rows.map(r=>[r.start,r.end])).toEqual([[1320,1440]]);
   expect(dayClassLayout([overnight],"2026-11-04","Asia/Jerusalem").rows.map(r=>[r.start,r.end])).toEqual([[0,120]]);
   expect(dayClassLayout([{...overnight,end:"2026-11-04T00:00:00+02:00"}],"2026-11-04","Asia/Jerusalem").rows).toEqual([]);
 });
 it("shows source room in either source order without inferring a missing room",()=>{expect(classRoom({...event,notes:"הרצאה\nחדר: 709 L L בראודה"})).toBe("L 709");expect(classRoom({...event,notes:"הרצאה\nחדר: M 209"})).toBe("M 209");expect(classRoom(event)).toBeNull();});
 it("only separates explicit classes and preserves exams/unknown/personal events",()=>{expect(isClassEvent(event)).toBe(true);expect(isClassEvent({...event,title:"מבחן בקורס"})).toBe(false);expect(isClassEvent({...event,notes:""})).toBe(false);expect(isClassEvent({...event,source:"google"})).toBe(false);expect(isClassEvent({...event,source:"timetable"})).toBe(true);});
 it("places exact local minutes and assigns separate lanes for overlaps",()=>{const layout=dayClassLayout([event,{...event,id:"other",start:"2026-11-01T07:00:00Z"}],"2026-11-01","Asia/Jerusalem");expect(layout.rows.map(r=>[r.start,r.end,r.lane])).toEqual([[510,600,0],[540,600,1]]);expect(layout.lanes).toBe(2);expect(dayClassLayout([event],"2026-11-02","Asia/Jerusalem").rows).toEqual([]);});
});
