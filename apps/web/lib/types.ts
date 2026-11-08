export type Task = {
  id: string;
  title: string;
  notes: string;
  priority: "low" | "medium" | "high";
  due: string | null;
  completed: boolean;
  created_at: string;
  academic_id?: string | null;
  academic_course_id?: string | null;
  academic_kind?: "assignment" | "exam" | null;
  academic_course_name?: string | null;
};
export type CalendarEvent = {
  id: string;
  title: string;
  notes: string;
  start: string;
  end: string;
  all_day: boolean;
  created_at: string;
  source?: "personal" | "timetable" | "assignment" | "exam" | "google" | "moodle" | "braude";
  source_url?: string;
  course_id?: string | null;
  academic_id?: string | null;
};
export type Settings = {
  display_name: string;
  language: "he" | "en";
  theme: "dark" | "light" | "system";
  timezone: string;
};
export type View = "dashboard" | "tasks" | "calendar" | "settings" | "academic" | "timetable";
export type Translate = (he: string, en: string) => string;
