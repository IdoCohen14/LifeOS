"use client";
import { useState, type FormEvent } from "react";
import type { AcademicKind, AcademicRecord, Course, Term } from "@/lib/academic";
import type { Settings, Translate } from "@/lib/types";
import { localInput, localInstant } from "@/lib/dates";
import { ApiError } from "@/lib/api";
import { Modal } from "./ui/dialog";
import { Button } from "./ui/button";

export type AcademicEditor = {
  kind: AcademicKind;
  record?: AcademicRecord;
  courseId?: string;
  termId?: string;
};
type Field = {
  name: string;
  he: string;
  en: string;
  type?: string;
  required?: boolean;
  max?: number;
  min?: number;
  step?: string;
  options?: { value: string; label: string }[];
};

export function AcademicForm({
  editor,
  terms,
  courses = [],
  settings,
  t,
  onClose,
  onSave,
}: {
  editor: AcademicEditor;
  terms: Term[];
  courses?: Course[];
  settings: Settings;
  t: Translate;
  onClose: () => void;
  onSave: (kind: AcademicKind, body: unknown, id?: string) => Promise<void>;
}) {
  const [timezone] = useState(settings.timezone);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dirty, setDirty] = useState(false);
  const record = editor.record as
    (AcademicRecord & Record<string, unknown>) | undefined;
  const [itemKind, setItemKind] = useState(String(record?.kind ?? "assignment"));
  const titles = {
    terms: t("סמסטר", "Term"),
    courses: t("קורס", "Course"),
    items: t("מטלה או מבחן", "Assignment or exam"),
    timetable: t("מפגש שבועי", "Weekly session"),
    grades: t("ציון", "Grade"),
  };
  const [timed, setTimed] = useState(
    Boolean(record?.due && String(record.due).length > 10),
  );
  const [dueValue, setDueValue] = useState(() =>
    record?.due
      ? String(record.due).length > 10
        ? localInput(String(record.due), timezone)
        : String(record.due)
      : "",
  );
  const baseNames: Field[] =
    editor.kind === "terms"
      ? [
          {
            name: "name",
            he: "שם הסמסטר",
            en: "Term name",
            required: true,
            max: 120,
          },
          {
            name: "start_date",
            he: "תאריך התחלה",
            en: "Start date",
            type: "date",
            required: true,
          },
          {
            name: "end_date",
            he: "תאריך סיום",
            en: "End date",
            type: "date",
            required: true,
          },
        ]
      : editor.kind === "courses"
        ? [
            {
              name: "name",
              he: "שם הקורס",
              en: "Course name",
              required: true,
              max: 160,
            },
            {
              name: "term_id",
              he: "סמסטר",
              en: "Term",
              required: true,
              options: terms.map((term) => ({
                value: term.id,
                label: term.name,
              })),
            },
            { name: "code", he: "קוד קורס", en: "Course code", max: 50 },
            { name: "instructor", he: "מרצה", en: "Instructor", max: 120 },
            {
              name: "credits",
              he: "נקודות זכות",
              en: "Credits",
              type: "number",
              min: 0,
              max: 60,
              step: "0.5",
            },
            {
              name: "color",
              he: "צבע הקורס",
              en: "Course color",
              type: "color",
            },
          ]
        : editor.kind === "items"
          ? [
              {
                name: "title",
                he: "כותרת",
                en: "Title",
                required: true,
                max: 240,
              },
              {
                name: "kind",
                he: "סוג",
                en: "Type",
                options: [
                  { value: "assignment", label: t("מטלה", "Assignment") },
                  { value: "exam", label: t("מבחן", "Exam") },
                ],
              },
              {
                name: "due",
                he: "מועד",
                en: "Due date",
                type: timed ? "datetime-local" : "date",
                required: true,
              },
              {
                name: "effort_hours",
                he: "שעות עבודה משוערות",
                en: "Estimated effort (hours)",
                type: "number",
                min: 0,
                max: 1000,
                step: "0.5",
              },
              {
                name: "duration_minutes",
                he: "משך מבחן בדקות",
                en: "Exam duration (minutes)",
                type: "number",
                min: 1,
                max: 720,
              },
              {
                name: "notes",
                he: "הערות",
                en: "Notes",
                type: "textarea",
                max: 10000,
              },
            ]
          : editor.kind === "timetable"
            ? [
                {
                  name: "weekday",
                  he: "יום בשבוע",
                  en: "Weekday",
                  options: Array.from({ length: 7 }, (_, i) => ({
                    value: String(i),
                    label: new Intl.DateTimeFormat(settings.language, {
                      weekday: "long",
                      timeZone: "UTC",
                    }).format(new Date(Date.UTC(2026, 9, 25 + i))),
                  })),
                },
                {
                  name: "start_time",
                  he: "שעת התחלה",
                  en: "Start time",
                  type: "time",
                  required: true,
                },
                {
                  name: "end_time",
                  he: "שעת סיום",
                  en: "End time",
                  type: "time",
                  required: true,
                },
                { name: "location", he: "מיקום", en: "Location", max: 240 },
                {
                  name: "timezone",
                  he: "אזור זמן",
                  en: "Timezone",
                  required: true,
                  max: 80,
                },
              ]
            : [
                {
                  name: "title",
                  he: "רכיב הציון",
                  en: "Grade title",
                  required: true,
                  max: 240,
                },
                {
                  name: "score",
                  he: "ציון שהתקבל",
                  en: "Score",
                  type: "number",
                  required: true,
                  min: 0,
                  step: "0.01",
                },
                {
                  name: "maximum",
                  he: "ציון מרבי",
                  en: "Maximum score",
                  type: "number",
                  required: true,
                  min: 0.01,
                  max: 100000,
                  step: "0.01",
                },
                {
                  name: "weight",
                  he: "משקל באחוזים (רשות)",
                  en: "Weight percent (optional)",
                  type: "number",
                  min: 0.01,
                  max: 100,
                  step: "0.01",
                },
              ];
  const names: Field[] = (editor.kind === "items" || editor.kind === "timetable") && !editor.courseId && !record
    ? [{ name: "course_id", he: "קורס", en: "Course", required: true, options: [
      {value:"",label:t("בחרו קורס", "Choose a course")},
      ...courses.map(course=>({value:course.id,label:`${course.name} · ${terms.find(term=>term.id===course.term_id)?.name ?? ""}`})),
    ] }, ...baseNames] : baseNames;
  const defaults: Record<string, unknown> = {
    term_id: terms.some(term=>term.id===editor.termId) ? editor.termId : undefined,
    credits: 0,
    color: "#a597ff",
    kind: "assignment",
    effort_hours: 0,
    duration_minutes: 120,
    weekday: 0,
    timezone: timezone,
    maximum: 100,
  };
  function close() {
    if (
      !busy &&
      (!dirty ||
        window.confirm(t("לסגור בלי לשמור?", "Discard unsaved changes?")))
    )
      onClose();
  }
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(e.currentTarget);
    const body: Record<string, unknown> = {};
    for (const field of names) {
      const value = String(form.get(field.name) ?? "").trim();
      body[field.name] =
        field.type === "number"
          ? value
            ? Number(value)
            : field.name === "weight"
              ? null
              : 0
          : value;
    }
    if (editor.courseId) body.course_id = editor.courseId;
    if (editor.kind === "timetable") body.weekday = Number(body.weekday);
    if (editor.kind === "items") {
      body.completed = body.kind === "exam" ? Boolean(record?.completed) : form.has("completed");
      try {
        body.due = timed
          ? localInstant(String(body.due), timezone, record?.due ? String(record.due) : null)
          : body.due;
      } catch {
        setError(
          t(
            "השעה אינה תקינה במעבר שעון. בחרו שעה אחרת.",
            "This time is missing or repeated during DST. Choose another.",
          ),
        );
        setBusy(false);
        return;
      }
    }
    try {
      await onSave(editor.kind, body, record?.id);
      onClose();
    } catch (error) {
      setError(
        error instanceof ApiError && error.status === 503 && error.message === "academic_busy"
          ? t("מסד הנתונים עסוק. הניסיון הזה לא שמר דבר. המתינו מעט ונסו שוב.", "The database is busy. Nothing was saved by this attempt. Wait a moment and retry.")
          : error instanceof Error && error.message.includes("associated")
          ? t(
              "יש להסיר תחילה את הפריטים המקושרים.",
              "Remove linked records first.",
            )
          : t(
              "לא ניתן לשמור. בדקו את התאריכים, הציונים והחיבור המקומי ונסו שוב.",
              "Could not save. Check dates, scores and the local connection, then retry.",
            ),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      open
      onClose={close}
      title={`${record ? t("עריכת", "Edit") : t("הוספת", "Add")} ${titles[editor.kind]}`}
      description={t(
        "נתונים ידניים שנשמרים במרחב המקומי שלך.",
        "Manual records stored in your local workspace.",
      )}
      closeLabel={t("סגירה", "Close")}
    >
      <form
        className="form-stack"
        onSubmit={submit}
        onChange={() => setDirty(true)}
      >
        {editor.kind === "items" && (
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={timed}
              onChange={(e) => {
                const checked = e.target.checked;
                setDueValue((value) =>
                  value
                    ? checked
                      ? `${value.slice(0, 10)}T12:00`
                      : value.slice(0, 10)
                    : "",
                );
                setTimed(checked);
              }}
            />
            {t("מועד עם שעה מדויקת", "Include a specific time")}
          </label>
        )}
        {names.map((field) => {
          let value = record?.[field.name] ?? defaults[field.name] ?? "";
          if (field.name === "due" && value && timed)
            value =
              String(value).length > 10
                ? localInput(String(value), timezone)
                : `${value}T12:00`;
          else if (field.name === "due" && value)
            value =
              String(value).length > 10
                ? localInput(String(value), timezone).slice(0, 10)
                : value;
          return (
            <label key={field.name}>
              {t(field.he, field.en)}
              {field.options ? (
                <select
                  name={field.name}
                  aria-label={t(field.he, field.en)}
                  defaultValue={String(value || field.options[0]?.value)}
                  onChange={field.name === "kind" ? (e) => setItemKind(e.target.value) : undefined}
                  required={field.required}
                >
                  {field.options.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              ) : field.name === "due" ? (
                <input
                  name="due"
                  type={timed ? "datetime-local" : "date"}
                  value={dueValue}
                  required
                  onChange={(e) => setDueValue(e.target.value)}
                />
              ) : field.type === "textarea" ? (
                <textarea
                  name={field.name}
                  defaultValue={String(value)}
                  maxLength={field.max}
                  rows={3}
                />
              ) : (
                <input
                  name={field.name}
                  type={field.type ?? "text"}
                  defaultValue={String(value)}
                  required={field.required}
                  maxLength={field.type === "number" ? undefined : field.max}
                  max={field.type === "number" ? field.max : undefined}
                  min={field.min}
                  step={field.step}
                  autoComplete="off"
                />
              )}
            </label>
          );
        })}
        {editor.kind === "items" && itemKind !== "exam" && (
          <label className="checkbox-label">
            <input
              type="checkbox"
              name="completed"
              defaultChecked={Boolean(record?.completed)}
            />
            {t("הושלם", "Completed")}
          </label>
        )}
        {editor.kind === "timetable" && (
          <p className="field-help">
            {t(
              "המפגש חוזר מדי שבוע לאורך הסמסטר. שעות לא קיימות או כפולות במעבר שעון יידחו.",
              "Repeats weekly within the term. Missing or repeated DST wall times are rejected.",
            )}
          </p>
        )}
        {error && (
          <p className="error-message" role="alert">
            {error}
          </p>
        )}
        <div className="form-actions">
          <Button type="submit" disabled={busy}>
            {busy ? t("שומר…", "Saving…") : t("שמירה", "Save")}
          </Button>
          <Button variant="secondary" onClick={close} disabled={busy}>
            {t("ביטול", "Cancel")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
