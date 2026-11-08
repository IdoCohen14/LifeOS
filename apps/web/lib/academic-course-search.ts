import type { Course } from "./academic";

export function matchingCourses(courses:Course[],query:string) {
  const needle=query.trim().toLowerCase();
  return courses.filter(course=>!needle||[course.name,course.code,course.instructor].some(value=>(value??"").toLowerCase().includes(needle)));
}
