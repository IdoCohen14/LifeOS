export type Term = {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
};
export type Course = {
  source?: "braude";
  credits_known?: boolean;
  id: string;
  term_id: string;
  name: string;
  code: string;
  instructor: string;
  credits: number;
  color: string;
};
export type AcademicItem = {
  id: string;
  course_id: string;
  task_id: string;
  title: string;
  notes: string;
  kind: "assignment" | "exam";
  due: string;
  effort_hours: number;
  duration_minutes: number;
  completed: boolean;
};
export type Slot = {
  id: string;
  course_id: string;
  weekday: number;
  start_time: string;
  end_time: string;
  timezone: string;
  location: string;
};
export type Grade = {
  id: string;
  course_id: string;
  title: string;
  score: number;
  maximum: number;
  weight: number | null;
};
export type StudyDocument = {
  id: string;
  course_id: string;
  filename: string;
  size: number;
  text_status: "indexed" | "no_text" | "truncated";
  created_at: string;
};
export type DocumentSection = { reference: string; text: string };
export type SearchHit = {
  document_id: string;
  course_id: string;
  filename: string;
  reference: string;
  excerpt: string;
};
export type AcademicData = {
  terms: Term[];
  courses: Course[];
  items: AcademicItem[];
  timetable: Slot[];
  grades: Grade[];
  documents: StudyDocument[];
};
export type AcademicKind =
  "terms" | "courses" | "items" | "timetable" | "grades";
export type AcademicRecord = Term | Course | AcademicItem | Slot | Grade;
export function weightedGrade(grades: Grade[]): number | null {
  if (
    !grades.length ||
    grades.some((g) => g.weight === null) ||
    Math.abs(grades.reduce((sum, g) => sum + (g.weight ?? 0), 0) - 100) >
      0.00001
  )
    return null;
  return grades.reduce(
    (sum, g) => sum + (g.score / g.maximum) * (g.weight ?? 0),
    0,
  );
}
export function sourceReference(reference: string, he: boolean) {
  const [kind, number] = reference.split(":");
  return (
    ({
      page: he ? "עמוד" : "Page",
      slide: he ? "שקופית" : "Slide",
      paragraph: he ? "פסקה" : "Paragraph",
      document: he ? "מסמך" : "Document",
    }[kind] ?? kind) + (number ? ` ${number}` : "")
  );
}
