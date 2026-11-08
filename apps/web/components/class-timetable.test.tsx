import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import {afterEach,expect,it} from "vitest";
import {ClassTimetable} from "./class-timetable";
afterEach(cleanup);
it("shows exact session span and navigates actual dated weeks",()=>{
 render(<ClassTimetable events={[{id:"fixture",title:"Fixture class",notes:"הרצאה\nחדר: 709 L L בראודה",source:"braude",all_day:false,start:"2026-11-01T06:30:00Z",end:"2026-11-01T08:00:00Z",created_at:"2026-01-01T00:00:00Z"}]} today="2026-11-01" settings={{language:"en",timezone:"Asia/Jerusalem",theme:"dark",display_name:""}} t={(_he,en)=>en}/>);
 const block=screen.getByRole("button",{name:/08:30–10:00.*L 709.*Fixture class/});expect(block).toHaveStyle({height:"135px"});expect(screen.getByText("L 709")).toHaveAttribute("dir","ltr");
 fireEvent.click(block);expect(screen.getByRole("dialog")).toBeInTheDocument();fireEvent.click(screen.getByRole("button",{name:"Close"}));
 fireEvent.click(screen.getByRole("button",{name:"Next week"}));expect(screen.getByRole("status")).toHaveTextContent("No synced classes this week.");
});
