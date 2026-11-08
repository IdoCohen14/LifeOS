import { expect, it } from "vitest";
import { matchingCourses } from "./academic-course-search";
import type { Course } from "./academic";
const courses=[{id:"a",name:"Algebra",code:"MAT101",instructor:"Dr Cohen"},{id:"b",name:"פיזיקה",code:"PHY101",instructor:"Dr Smith"}] as Course[];
it("matches course name/code/instructor case-insensitively and trims query",()=>{
 expect(matchingCourses(courses," algebra ").map(c=>c.id)).toEqual(["a"]);
 expect(matchingCourses(courses,"phy101").map(c=>c.id)).toEqual(["b"]);
 expect(matchingCourses(courses,"sMiTh").map(c=>c.id)).toEqual(["b"]);
 expect(matchingCourses(courses,"פיז").map(c=>c.id)).toEqual(["b"]);
});
it("keeps input order/references and treats blank query as all courses",()=>{
 const before=JSON.stringify(courses);
 expect(matchingCourses(courses,"   ")).toEqual(courses);
 expect(matchingCourses(courses,"unknown")).toEqual([]);
 expect(matchingCourses(courses,"MAT")[0]).toBe(courses[0]);
 expect(JSON.stringify(courses)).toBe(before);
});
