"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  Check,
  Pencil,
  Plus,
  Trash2,
  LoaderCircle,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { dayKey, dueDay, formatDay, formatTime } from "@/lib/dates";
import {
  weightedGrade,
  type AcademicData,
  type AcademicKind,
  type AcademicRecord,
  type AcademicItem,
  type Grade,
  type Slot,
} from "@/lib/academic";
import type { CalendarEvent, Settings, Task, Translate } from "@/lib/types";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";
import { AcademicForm, type AcademicEditor } from "./academic-form";
import { CourseDocuments } from "./course-documents";
import { AcademicExams } from "./academic-exams";
import { AcademicDeadlines } from "./academic-deadlines";
import { TaskPlanner } from "./task-planner";
import { ClassTimetable } from "./class-timetable";
import { AcademicTimetable } from "./academic-timetable";
import { AcademicStartGuide } from "./academic-start-guide";
import { matchingCourses } from "@/lib/academic-course-search";
import { TimetableBatchEntry } from "./timetable-batch";
import { CourseBatchEntry } from "./course-batch";

const empty: AcademicData = {
  terms: [],
  courses: [],
  items: [],
  timetable: [],
  grades: [],
  documents: [],
};
export function AcademicView({
  settings,
  sourceEvents = [],
  csrf,
  t,
  courseId,
  onSelect,
  onChanged,
  onUnauthorized,
  tasks = [],
  today = dayKey(new Date(), settings.timezone),
  now = new Date(),
  onDay,
}: {
  settings: Settings;
  sourceEvents?: CalendarEvent[];
  csrf: string;
  t: Translate;
  courseId: string | null;
  onSelect: (id: string | null) => void;
  onChanged: () => Promise<void>;
  onUnauthorized: () => void;
  tasks?: Task[];
  today?: string;
  now?: Date;
  onDay?: (day: string) => void;
}) {
  const [data, setData] = useState(empty);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState<AcademicEditor | null>(null);
  const [deleting, setDeleting] = useState<{
    kind: AcademicKind;
    record: AcademicRecord;
  } | null>(null);
  const [tab, setTab] = useState<
    "items" | "timetable" | "grades" | "documents"
  >("items");
  const [termFilter, setTermFilter] = useState("all");
  const [overview, setOverview] = useState<"timetable" | "assignments" | "exams" | "courses">("timetable");
  const [showCompletedItems, setShowCompletedItems] = useState(false);
  const [courseQuery,setCourseQuery]=useState("");
  const scopedCourses=data.courses.filter(course=>termFilter==="all"||course.term_id===termFilter);
  const scopedCourseIds=new Set(scopedCourses.map(course=>course.id));
  const visibleCourses=matchingCourses(scopedCourses,courseQuery);
  const loadGeneration = useRef(0);
  const load = useCallback(async () => {
    const current = ++loadGeneration.current;
    const keys = [
      "terms",
      "courses",
      "items",
      "timetable",
      "grades",
      "documents",
    ] as const;
    try {
      const values = await Promise.all(keys.map((key) => api(`academic/${key}`)));
      if (loadGeneration.current !== current) return false;
      setData(Object.fromEntries(keys.map((key, i) => [key, values[i]])) as AcademicData);
      return true;
    } catch (error) {
      if (loadGeneration.current !== current) return false;
      throw error;
    } finally {
      if (loadGeneration.current === current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        if (await load()) setError("");
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) onUnauthorized();
        setError(error instanceof ApiError && error.message === "academic_resource_limit" ? "resource" : "load");
      }
    })();
    return () => { active = false; loadGeneration.current += 1; };
  }, [load, onUnauthorized, csrf]);
  async function refresh() {
    if (!await load()) return false;
    await onChanged();
    return true;
  }
  async function afterWrite() {
    const current = loadGeneration.current + 1;
    try {
      await refresh();
    } catch (error) {
      if (loadGeneration.current !== current) return;
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      setError("saved_refresh");
    }
  }
  function failed(error: unknown) {
    if (error instanceof ApiError && error.message === "academic_resource_limit") {setError("resource");return;}
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
    setError(
      error instanceof ApiError && error.status === 409
        ? t(
            "יש להסיר תחילה מטלות, מפגשים, ציונים וקבצים שמקושרים לפריט.",
            "Remove linked assignments, sessions, grades and files first.",
          )
        : t(
            "הפעולה נכשלה. בדקו את החיבור ונסו שוב.",
            "Operation failed. Check connection and retry.",
          ),
    );
  }
  async function save(kind: AcademicKind, body: unknown, id?: string) {
    try {
      await api(
        `academic/${kind}${id ? `/${id}` : ""}`,
        id ? "PUT" : "POST",
        body,
        csrf,
      );
      setError("");
      await afterWrite();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      throw error;
    }
  }
  async function toggle(item: AcademicItem) {
    setBusy(true);
    try {
      await save("items", { ...item, completed: !item.completed }, item.id);
    } catch (error) {
      failed(error);
    } finally {
      setBusy(false);
    }
  }
  function planAction(item: AcademicItem) {
    const task = tasks.find(task => task.id === item.task_id);
    if (!onDay || item.completed || !task || task.completed) return null;
    return <div className="academic-plan-action"><TaskPlanner compact disabled={busy || !!error} tasks={[task]} settings={settings} today={today} csrf={csrf} t={t} onChanged={async()=>{await refresh();}} onUnauthorized={onUnauthorized} onDay={onDay}/></div>;
  }
  const course = data.courses.find((course) => course.id === courseId);
  const items = data.items.filter((item) => item.course_id === courseId);
  const slots = data.timetable
    .filter((slot) => slot.course_id === courseId)
    .sort(
      (a, b) =>
        a.weekday - b.weekday || a.start_time.localeCompare(b.start_time),
    );
  const grades = data.grades.filter((grade) => grade.course_id === courseId);
  const documents = data.documents.filter((doc) => doc.course_id === courseId);
  const average = weightedGrade(grades);
  const assignments = items.filter(item => item.kind === "assignment");
  const completed = assignments.filter((item) => item.completed).length;
  const title = (record: AcademicRecord) =>
    "name" in record
      ? record.name
      : "title" in record
        ? record.title
        : t("מפגש שבועי", "Weekly session");
  function actions(kind: AcademicKind, record: AcademicRecord) {
    return (
      <div className="row-actions">
        <Button
          variant="ghost"
          size="icon"
          aria-label={`${t("עריכה", "Edit")}: ${title(record)}`}
          disabled={busy}
          onClick={() => setEditor({ kind, record, courseId: course?.id })}
        >
          <Pencil size={16} aria-hidden="true" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`${t("מחיקה", "Delete")}: ${title(record)}`}
          disabled={busy}
          onClick={() => {
            setError("");
            setDeleting({ kind, record });
          }}
        >
          <Trash2 size={16} aria-hidden="true" />
        </Button>
      </div>
    );
  }
  const add = () =>
    setEditor({
      kind: tab === "documents" ? "items" : tab,
      courseId: course?.id,
    });
  if (loading)
    return (
      <section className="panel academic-loading" aria-live="polite">
        <LoaderCircle className="spin" aria-hidden="true" />
        {t("טוען קורסים…", "Loading courses…")}
      </section>
    );
  return (
    <div className="academic-workspace">
      {error && (
        <div className="notice" role="alert">
          <span>
            {error === "resource"
              ? t("כמות הנתונים או משך הטעינה חרגו מהמגבלה. לא נטענה רשימה מלאה; אם מוצג מידע קודם, הוא עשוי להיות לא מעודכן. נסו שוב, ואם הבעיה חוזרת פנו לעזרה.","The data size or loading time exceeded the limit. A complete list was not loaded; any previous view may be outdated. Retry, and seek help if this persists.")
              : error === "load"
              ? t(
                  "לא ניתן לטעון קורסים. נסו שוב.",
                  "Could not load courses. Retry.",
                )
              : error === "saved_refresh"
                ? t(
                    "השינוי נשמר, אך התצוגה לא התעדכנה. רעננו לפני פעולה נוספת.",
                    "Saved, but the view is outdated. Refresh before another action.",
                  )
                : error}
          </span>
          <Button
            variant="secondary"
            onClick={async () => {
              const current = loadGeneration.current + 1;
              try {
                if (await refresh() && loadGeneration.current === current) setError("");
              } catch (error) {
                if (loadGeneration.current === current) failed(error);
              }
            }}
          >
            {t("ניסיון נוסף", "Retry")}
          </Button>
        </div>
      )}
      {!course ? (
        <>
          <div className="academic-toolbar">
            <div>
              <h2>{t("הלימודים שלי", "My studies")}</h2>
              <p className="muted">
                {t(
                  "התקדמות, מועדים וחומרי לימוד במקום אחד.",
                  "Progress, deadlines and study materials, together.",
                )}
              </p>
            </div>
            <details className="academic-manual-tools"><summary>{t("אפשרויות ידניות נוספות", "Additional manual options")}</summary><div className="toolbar-group">
              <TimetableBatchEntry terms={data.terms} courses={scopedCourses} csrf={csrf} t={t} onChanged={async()=>{await refresh();}} onUnauthorized={onUnauthorized}/>
              <CourseBatchEntry terms={data.terms} initialTerm={termFilter==='all'?undefined:termFilter} csrf={csrf} t={t} onChanged={async()=>{await refresh();}} onUnauthorized={onUnauthorized}/>
              <Button
                variant="secondary"
                onClick={() => setEditor({ kind: "terms" })}
              >
                <CalendarDays size={16} aria-hidden="true" />
                {t("סמסטר חדש", "New term")}
              </Button>
              <Button
                disabled={!data.terms.length}
                onClick={() => setEditor({ kind: "courses", termId: termFilter === "all" ? undefined : termFilter })}
              >
                <Plus size={16} aria-hidden="true" />
                {t("קורס חדש", "New course")}
              </Button>
              <Button variant="secondary" disabled={!data.courses.some(course=>termFilter==="all"||course.term_id===termFilter) || !!error} onClick={()=>setEditor({kind:"items"})}>
                <Plus size={16} aria-hidden="true"/>{t("מטלה או מבחן חדש", "New assignment or exam")}
              </Button>
              <Button variant="secondary" disabled={!data.courses.some(course=>termFilter==="all"||course.term_id===termFilter) || !!error} onClick={()=>setEditor({kind:"timetable"})}>
                <CalendarDays size={16} aria-hidden="true"/>{t("מפגש שבועי חדש", "New weekly session")}
              </Button>
            </div></details>
          </div>
          <nav className="calm-academic-tabs" aria-label={t("תחומי לימודים", "Study sections")}>
            {(["timetable", "assignments", "exams", "courses"] as const).map(section => <button type="button" key={section} aria-pressed={overview === section} onClick={() => setOverview(section)}>{({timetable:t("מערכת שעות", "Timetable"), assignments:t("מטלות", "Assignments"), exams:t("מבחנים", "Exams"), courses:t("קורסים", "Courses")})[section]}</button>)}
          </nav>
          <details className="simple-filters academic-scope"><summary>{t("חיפוש וסינון קורסים", "Course search and filters")}{(termFilter!=="all"||courseQuery)&&<span>{t("סינון פעיל", "Filtered")}</span>}</summary><div className="academic-filter">
            <label>
              {t("סינון לפי סמסטר", "Filter by term")}
              <select
                aria-label={t("סינון לפי סמסטר", "Filter by term")}
                value={termFilter}
                onChange={(e) => setTermFilter(e.target.value)}
              >
                <option value="all">{t("כל הסמסטרים", "All terms")}</option>
                {data.terms.map((term) => (
                  <option key={term.id} value={term.id}>
                    {term.name}
                  </option>
                ))}
              </select>
            </label>
            <span className="subtle-badge">
              {t(
                data.courses.some(course=>course.source==="braude")?"קורסים מתחנת המידע · שיעורים מסונכרנים":"קורסים ומטלות בניהול ידני",
                data.courses.some(course=>course.source==="braude")?"Portal courses · synced classes":"Manually managed courses and assignments",
              )}
            </span>
          </div>
          <div className="academic-course-search">
            <label>{t("חיפוש קורסים", "Course search")}<input type="search" value={courseQuery} onChange={event=>setCourseQuery(event.target.value)} maxLength={160} placeholder={t("שם, קוד קורס או מרצה", "Name, course code or instructor")} autoComplete="off"/></label>
            {courseQuery&&<Button variant="ghost" onClick={()=>setCourseQuery("")}>{t("ניקוי חיפוש קורסים", "Clear course search")}</Button>}
            <span className="field-help" role="status">{t(`${visibleCourses.length} קורסים מוצגים`,`${visibleCourses.length} courses shown`)}</span>
          </div>
          {courseQuery.trim()&&!visibleCourses.length&&<p role="status" className="field-help course-search-empty">{t("לא נמצאו קורסים שתואמים לחיפוש ולסמסטר. אפשר לנקות את החיפוש או לבחור סמסטר אחר.","No courses match the search and term. Clear the search or choose another term.")}</p>}
          </details>
          {!data.courses.some(course=>course.source==="braude")&&<AcademicStartGuide hasTerm={termFilter==="all"?data.terms.length>0:data.terms.some(term=>term.id===termFilter)} hasCourse={scopedCourses.length>0} hasItem={data.items.some(item=>scopedCourseIds.has(item.course_id))} disabled={busy||!!error} t={t} onTerm={()=>setEditor({kind:"terms"})} onCourse={()=>setEditor({kind:"courses",termId:termFilter==="all"?undefined:termFilter})} onItem={()=>setEditor({kind:"items"})} onSession={()=>setEditor({kind:"timetable"})}/>}
          <section hidden={overview !== "assignments"} aria-label={t("מטלות", "Assignments")}><AcademicDeadlines key={termFilter} items={data.items} courses={visibleCourses} term={termFilter} settings={settings} today={today} now={now} busy={busy || !!error} t={t} onSelect={id=>{setTab("items");onSelect(id);}} onToggle={item=>void toggle(item)} renderPlan={planAction} />
          </section><section hidden={overview !== "exams"} aria-label={t("מבחנים", "Exams")}><AcademicExams key={`exams-${termFilter}`} items={data.items} courses={visibleCourses} term={termFilter} settings={settings} now={now} t={t} onSelect={id=>{setTab("items");onSelect(id);}} />
          </section><section hidden={overview !== "timetable"} aria-label={t("מערכת שעות", "Timetable")}>          {data.courses.some(course=>course.source==="braude")?<ClassTimetable courses={visibleCourses} events={sourceEvents.filter(event=>!!event.course_id&&visibleCourses.some(course=>course.id===event.course_id))} today={today} settings={settings} t={t}/>:<AcademicTimetable slots={data.timetable} courses={visibleCourses} terms={data.terms} term={termFilter} settings={settings} t={t} onSelect={id=>{setTab("timetable");onSelect(id);}}/>}
</section>
          <section hidden={overview !== "courses"} aria-label={t("הקורסים שלי", "My courses")}><h2 className="calm-course-list-title">{t("הקורסים בסמסטר", "Courses in this term")}</h2>
          <div className="course-grid">
            {visibleCourses
              .map((course) => {
                const list = data.items.filter(
                  (item) => item.course_id === course.id && item.kind === "assignment",
                );
                const done = list.filter((item) => item.completed).length;
                return (
                  <button
                    className="course-card"
                    key={course.id}
                    onClick={() => {setTab("items");onSelect(course.id);}}
                    style={{ borderBlockStartColor: course.color }}
                  >
                    <div className="course-card-top">
                      <BookOpen
                        size={23}
                        color={course.color}
                        aria-hidden="true"
                      />
                      <span className="subtle-badge">
                        {
                          data.terms.find((term) => term.id === course.term_id)
                            ?.name
                        }
                      </span>
                    </div>
                    <h3 dir="auto">{course.name}</h3>
                    <p dir="auto">
                      {course.code}
                      {course.code && course.instructor ? " · " : ""}
                      {course.instructor ||
                        (!course.code
                          ? t("ללא פרטי מרצה", "No instructor details")
                          : "")}
                    </p>
                    <div className="course-card-stats">
                      <span>
                        {course.source==="braude"&&!course.credits_known?t("נק״ז לא סופקו במקור", "Credits not provided by source"):<>{course.credits} {t("נק״ז", "credits")}</>}
                      </span>
                      <span>
                        {done}/{list.length} {t("הושלמו", "completed")}
                      </span>
                    </div>
                    <progress
                      max={list.length || 1}
                      value={done}
                      aria-label={t("התקדמות בקורס", "Course progress")}
                    />
                  </button>
                );
              })}
          </div>
          </section>
          {overview === "courses" && data.terms.length > 0 && (
            <details className="panel term-manager">
              <summary>
                {t("ניהול סמסטרים", "Manage terms")} ({data.terms.length})
              </summary>
              <ul className="academic-list">
                {data.terms.map((term) => (
                  <li key={term.id}>
                    <div className="academic-record-content">
                      <strong dir="auto">{term.name}</strong>
                      <p className="record-meta">
                        {formatDay(term.start_date, settings.language, {
                          dateStyle: "medium",
                        })}{" "}
                        —{" "}
                        {formatDay(term.end_date, settings.language, {
                          dateStyle: "medium",
                        })}
                      </p>
                    </div>
                    {actions("terms", term)}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      ) : (
        <>
          <div className="course-header">
            <Button variant="ghost" onClick={() => onSelect(null)}>
              <ArrowRight
                className="rtl-chevron"
                size={17}
                aria-hidden="true"
              />
              {t("כל הקורסים", "All courses")}
            </Button>
            <div className="course-heading">
              <span
                className="course-emblem"
                style={{ background: course.color + "20", color: course.color }}
              >
                <BookOpen size={28} aria-hidden="true" />
              </span>
              <div>
                <h2 dir="auto">{course.name}</h2>

              </div>
              {actions("courses", course)}
            </div>
            <details className="course-context"><summary>{t("על הקורס וההתקדמות", "Course details and progress")}</summary>                <p className="muted" dir="auto">
                  {[
                    course.code,
                    course.instructor,
                    data.terms.find((term) => term.id === course.term_id)?.name,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>            <div className="course-progress">
              <span>
                {completed}/{assignments.length}{" "}
                {t("מטלות הושלמו", "assignments completed")}
              </span>
              <progress
                max={assignments.length || 1}
                value={completed}
                aria-label={t("התקדמות בקורס", "Course progress")}
              />
            </div></details>
          </div>
          <div
            className="academic-tabs"
            role="tablist"
            aria-label={t("סביבת הקורס", "Course workspace")}
          >
            {(["items", "timetable", "grades", "documents"] as const).map(
              (key) => (
                <button
                  key={key}
                  role="tab"
                  aria-selected={tab === key}
                  aria-controls={`course-panel-${key}`}
                  id={`course-tab-${key}`}
                  tabIndex={tab === key ? 0 : -1}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                      const keys = [
                        "items",
                        "timetable",
                        "grades",
                        "documents",
                      ] as const;
                      const next =
                        keys[
                          (keys.indexOf(tab) +
                            (e.key === "ArrowRight" ? 1 : 3)) %
                            4
                        ];
                      setTab(next);
                      document.getElementById(`course-tab-${next}`)?.focus();
                    }
                  }}
                  onClick={() => setTab(key)}
                >
                  {key === "items"
                    ? t("מטלות ומבחנים", "Assignments & exams")
                    : key === "timetable"
                      ? t("מערכת שעות", "Timetable")
                      : key === "grades"
                        ? t("ציונים", "Grades")
                        : t("קבצים", "Files")}
                </button>
              ),
            )}
          </div>
          <section
            className="panel course-panel"
            role="tabpanel"
            id={`course-panel-${tab}`}
            aria-labelledby={`course-tab-${tab}`}
          >
            <div className="panel-heading">
              <h2>
                {tab === "items"
                  ? t("מה על הפרק", "What’s ahead")
                  : tab === "timetable"
                    ? t("השבוע בקורס", "Your weekly sessions")
                    : tab === "grades"
                      ? t("תמונת הציונים", "Your grades")
                      : t("ספריית הקורס", "Course library")}
              </h2>
              {tab !== "documents" && (
                <Button variant="secondary" onClick={add}>
                  <Plus size={16} aria-hidden="true" />
                  {tab === "items"
                    ? t("מטלה או מבחן", "Assignment or exam")
                    : tab === "timetable"
                      ? t("מפגש שבועי", "Weekly session")
                      : t("ציון חדש", "New grade")}
                </Button>
              )}
            </div>
            {tab === "items" && (
              <>
                <label className="completed-toggle"><input type="checkbox" checked={showCompletedItems} onChange={event=>setShowCompletedItems(event.target.checked)}/>{t("להציג גם פריטים שהושלמו", "Include completed items")}</label>
                <ul className="academic-list">
                  {assignments.filter(item=>showCompletedItems||!item.completed)
                    .sort(
                      (a, b) =>
                        Number(a.completed) - Number(b.completed) ||
                        a.due.localeCompare(b.due),
                    )
                    .map((item) => (
                      <li key={item.id}>
                        <button
                          className={`task-check ${item.completed ? "academic-complete" : ""}`}
                          role="checkbox"
                          aria-checked={item.completed}
                          aria-label={`${t("השלמה", "Complete")}: ${item.title}`}
                          onClick={() => toggle(item)}
                          disabled={busy}
                        >
                          {item.completed && (
                            <Check size={14} aria-hidden="true" />
                          )}
                        </button>
                        <div className="academic-record-content">
                          <strong dir="auto">{item.title}</strong>
                          <div className="record-meta">
                            <span
                              className={`subtle-badge ${item.kind === "exam" ? "exam-badge" : ""}`}
                            >
                              {item.kind === "exam"
                                ? t("מבחן", "Exam")
                                : t("מטלה", "Assignment")}
                            </span>
                            <span>
                              {formatDay(
                                dueDay(item.due, settings.timezone),
                                settings.language,
                                { day: "numeric", month: "long" },
                              )}
                              {item.due.length > 10
                                ? ` · ${formatTime(item.due, settings.language, settings.timezone)}`
                                : ""}
                            </span>
                          </div>
                          <details className="item-extra"><summary>{t("פרטים ואפשרויות", "Details and options")}</summary>
                            {item.effort_hours > 0 && <p>{item.effort_hours} {t("שעות משוערות", "estimated hours")}</p>}
                            {item.notes && <p className="record-notes" dir="auto">{item.notes}</p>}
                            {planAction(item)}
                            {actions("items", item)}
                          </details>
                        </div>
                      </li>
                    ))}
                </ul>
                {!assignments.filter(item=>showCompletedItems||!item.completed).length && (
                  <p className="academic-empty">
                    {t(
                      "אין מטלות פתוחות בקורס הזה.",
                      "No open assignments in this course.",
                    )}
                  </p>
                )}
              </>
            )}
            {tab === "timetable" && course.source==="braude" && <ClassTimetable events={sourceEvents.filter(event=>event.course_id===course.id)} today={today} settings={settings} t={t}/>}
            {tab === "timetable" && course.source!=="braude" && (
              <>
                <ul className="academic-list">
                  {slots.map((slot: Slot) => (
                    <li key={slot.id}>
                      <CalendarDays size={21} aria-hidden="true" />
                      <div className="academic-record-content">
                        <strong>
                          {new Intl.DateTimeFormat(settings.language, {
                            weekday: "long",
                            timeZone: "UTC",
                          }).format(
                            new Date(Date.UTC(2026, 9, 25 + slot.weekday)),
                          )}
                        </strong>
                        <p className="record-meta">
                          <bdi>
                            {slot.start_time}–{slot.end_time}
                          </bdi>
                          <bdi>{slot.timezone}</bdi>
                          <span dir="auto">{slot.location}</span>
                        </p>
                      </div>
                      {actions("timetable", slot)}
                    </li>
                  ))}
                </ul>
                {!slots.length && (
                  <p className="academic-empty">
                    {t(
                      "הוסיפו מפגש שבועי. הוא יופיע ביומן לאורך הסמסטר.",
                      "Add a weekly session to show it in your calendar throughout the term.",
                    )}
                  </p>
                )}
              </>
            )}
            {tab === "grades" && (
              <>
                <div className="grade-summary">
                  <span>{t("ציון משוקלל סופי", "Final weighted grade")}</span>
                  <strong>
                    {average === null
                      ? "—"
                      : new Intl.NumberFormat(settings.language, {
                          maximumFractionDigits: 2,
                        }).format(average)}
                  </strong>
                  <p>
                    {average === null
                      ? t(
                          "יוצג רק כאשר לכל הציונים יש משקל וסך המשקלים הוא 100%.",
                          "Available only when every grade has a weight and weights total 100%.",
                        )
                      : t(
                          "מחושב מהציונים והמשקלים שהזנת.",
                          "Calculated from your entered scores and weights.",
                        )}
                  </p>
                </div>
                <ul className="academic-list">
                  {grades.map((grade: Grade) => (
                    <li key={grade.id}>
                      <div className="academic-record-content">
                        <strong dir="auto">{grade.title}</strong>
                        <p className="record-meta">
                          {grade.weight === null
                            ? t("משקל לא הוגדר", "No weight specified")
                            : `${grade.weight}% ${t("מהציון", "weight")}`}
                        </p>
                      </div>
                      <bdi className="grade-number">
                        {grade.score}/{grade.maximum}
                      </bdi>
                      {actions("grades", grade)}
                    </li>
                  ))}
                </ul>
                {!grades.length && (
                  <p className="academic-empty">
                    {t(
                      "לא הוזנו ציונים. לא ננחש ציונים חסרים.",
                      "No grades entered. Missing grades are never guessed.",
                    )}
                  </p>
                )}
              </>
            )}
            {tab === "documents" && (
              <CourseDocuments
                courseId={course.id}
                documents={documents}
                csrf={csrf}
                settings={settings}
                t={t}
                onChanged={afterWrite}
                onUnauthorized={onUnauthorized}
              />
            )}
          </section>
          <AcademicExams items={items} courses={data.courses.filter(value=>value.id===course.id)} term="all" settings={settings} now={now} t={t} renderActions={item=>actions("items",item)} />
        </>
      )}
      {editor && (
        <AcademicForm
          editor={editor}
          terms={data.terms}
          courses={scopedCourses}
          settings={settings}
          t={t}
          onClose={() => setEditor(null)}
          onSave={save}
        />
      )}
      {deleting && (
        <Modal
          open
          onClose={() => {
            if (!busy) setDeleting(null);
          }}
          title={t("למחוק את הפריט?", "Delete this record?")}
          description={title(deleting.record)}
          closeLabel={t("סגירה", "Close")}
        >
          <p className="muted">
            {t(
              "פריט מקושר יימחק גם מהמשימות ומהיומן. אי אפשר לבטל את הפעולה.",
              "A linked item is also removed from tasks and calendar. This cannot be undone.",
            )}
          </p>
          <div className="form-actions">
            <Button
              variant="danger"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await api(
                    `academic/${deleting.kind}/${deleting.record.id}`,
                    "DELETE",
                    undefined,
                    csrf,
                  );
                  if (
                    deleting.kind === "courses" &&
                    deleting.record.id === courseId
                  )
                    onSelect(null);
                  setDeleting(null);
                  await refresh();
                } catch (error) {
                  failed(error);
                  setDeleting(null);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {t("מחיקה", "Delete")}
            </Button>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => setDeleting(null)}
            >
              {t("ביטול", "Cancel")}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
