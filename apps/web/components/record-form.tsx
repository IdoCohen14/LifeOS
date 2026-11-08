"use client";
import { useState, type FormEvent } from "react";
import { Temporal } from "@js-temporal/polyfill";
import type { CalendarEvent, Settings, Task, Translate } from "@/lib/types";
import { localInput, localInstant, shiftDay } from "@/lib/dates";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";

export type Editor =
  | { kind: "task"; record?: Task; draft?: {title:string;notes:string} }
  | { kind: "event"; record?: CalendarEvent; day?: string; draft?: {title:string;notes:string} };
export function RecordForm({
  editor,
  settings,
  t,
  onClose,
  onSave,
}: {
  editor: Editor;
  settings: Settings;
  t: Translate;
  onClose: () => void;
  onSave: (kind: "task" | "event", body: unknown, id?: string) => Promise<void>;
}) {
  const record = editor.record;
  const isTask = editor.kind === "task";
  const event = !isTask ? editor.record : undefined;
  const task = isTask ? editor.record : undefined;
  const draft = editor.draft;
  const defaultDay = editor.kind === "event" ? editor.day : undefined;
  const [timezone] = useState(settings.timezone);
  const [allDay, setAllDay] = useState(event?.all_day ?? false);
  const [startValue, setStartValue] = useState(() =>
    event
      ? event.all_day
        ? event.start
        : localInput(event.start, timezone)
      : defaultDay
        ? `${defaultDay}T09:00`
        : "",
  );
  const [endValue, setEndValue] = useState(() =>
    event
      ? event.all_day
        ? shiftDay(event.end, -1)
        : localInput(event.end, timezone)
      : defaultDay
        ? `${defaultDay}T10:00`
        : "",
  );
  function changeAllDay(value: boolean) {
    setStartValue((current) =>
      current
        ? value
          ? current.slice(0, 10)
          : `${current.slice(0, 10)}T09:00`
        : "",
    );
    setEndValue((current) =>
      current
        ? value
          ? current.slice(0, 10)
          : `${current.slice(0, 10)}T10:00`
        : "",
    );
    setAllDay(value);
  }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dirty, setDirty] = useState(false);
  function close() {
    if (
      !busy &&
      (!dirty ||
        window.confirm(
          t("לסגור בלי לשמור את השינויים?", "Discard unsaved changes?"),
        ))
    )
      onClose();
  }
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    const data = new FormData(e.currentTarget);
    const title = String(data.get("title")).trim();
    if (!title) {
      setError(t("יש להזין כותרת.", "Enter a title."));
      return;
    }
    let body;
    try {
      const notes = String(data.get("notes") || "");
      if (isTask) {
        const date = String(data.get("due") || "");
        const time = String(data.get("due_time") || "");
        body = {
          title,
          notes,
          priority: data.get("priority"),
          due: date
            ? time
              ? localInstant(`${date}T${time}`, timezone, task?.due)
              : date
            : null,
          completed: task?.completed ?? false,
        };
      } else {
        const start = String(data.get("start"));
        const end = String(data.get("end"));
        const nextStart = allDay ? start : localInstant(start, timezone, event?.all_day ? null : event?.start);
        const nextEnd = allDay ? shiftDay(end, 1) : localInstant(end, timezone, event?.all_day ? null : event?.end);
        if (allDay ? nextEnd <= nextStart : Temporal.Instant.compare(nextEnd, nextStart) <= 0) {
          setError(
            t("מועד הסיום חייב להיות אחרי ההתחלה.", "End must be after start."),
          );
          return;
        }
        body = {
          title,
          notes,
          start: nextStart,
          end: nextEnd,
          all_day: allDay,
        };
      }
    } catch {
      setError(
        t(
          "השעה לא קיימת או חוזרת במעבר שעון. יש לבחור שעה אחרת.",
          "This local time is missing or repeated during a clock change. Choose another time.",
        ),
      );
      return;
    }
    setBusy(true);
    try {
      await onSave(editor.kind, body, record?.id);
      onClose();
    } catch {
      setError(
        t(
          "השמירה נכשלה. בדקו שהשרת המקומי פועל ונסו שוב.",
          "Could not save. Check the local server and retry.",
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
      title={
        record
          ? t("עריכת פריט", "Edit item")
          : isTask
            ? t("משימה חדשה", "New task")
            : t("אירוע חדש", "New event")
      }
      description={
        isTask
          ? t("צעד קטן שמפנה מקום בראש.", "Make room for what matters.")
          : t(
              "אירוע אישי שנשמר ביומן המקומי שלך.",
              "A personal event in your local calendar.",
            )
      }
      closeLabel={t("סגירה", "Close")}
    >
      <form
        onSubmit={submit}
        onChange={() => setDirty(true)}
        className="form-stack"
      >
        <label>
          {t("כותרת", "Title")}
          <input
            name="title"
            required
            maxLength={240}
            defaultValue={record?.title ?? draft?.title ?? ""}
            autoComplete="off"
            placeholder={
              isTask
                ? t("למשל, לסיים את התרגיל…", "e.g. Finish the assignment…")
                : t("למשל, מפגש לימוד…", "e.g. Study group…")
            }
          />
        </label>
        {isTask ? (
          <>
            <div className="form-grid">

              <label>
                {t("תאריך יעד", "Due date")}
                <input
                  type="date"
                  name="due"
                  defaultValue={
                    task?.due
                      ? task.due.length === 10
                        ? task.due
                        : localInput(task.due, timezone).slice(0, 10)
                      : ""
                  }
                />
              </label>
            </div>
            <details className="form-extra"><summary>{t("עדיפות ושעה מדויקת", "Priority and exact time")}</summary>              <label>
                {t("עדיפות", "Priority")}
                <select
                  name="priority"
                  aria-label={t("עדיפות", "Priority")}
                  defaultValue={task?.priority ?? "medium"}
                >
                  <option value="low">{t("נמוכה", "Low")}</option>
                  <option value="medium">{t("רגילה", "Normal")}</option>
                  <option value="high">{t("גבוהה", "High")}</option>
                </select>
              </label>            <label>
              {t("שעת יעד (רשות)", "Due time (optional)")}
              <input
                name="due_time"
                type="time"
                defaultValue={
                  task?.due && task.due.length > 10
                    ? localInput(task.due, timezone).slice(11)
                    : ""
                }
              />
            </label></details>
          </>
        ) : (
          <>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={allDay}
                onChange={(e) => changeAllDay(e.target.checked)}
              />
              {t("כל היום", "All day")}
            </label>
            <div className="form-grid">
              <label>
                {t("התחלה", "Start")}
                <input
                  required
                  name="start"
                  type={allDay ? "date" : "datetime-local"}
                  value={startValue}
                  onChange={(e) => setStartValue(e.target.value)}
                />
              </label>
              <label>
                {t("סיום", "End")}
                <input
                  required
                  name="end"
                  type={allDay ? "date" : "datetime-local"}
                  value={endValue}
                  onChange={(e) => setEndValue(e.target.value)}
                />
              </label>
            </div>
            <p className="field-help">
              {t("שעות מוצגות לפי", "Times use")} <bdi>{timezone}</bdi>
            </p>
          </>
        )}
        <details className="form-extra"><summary>{t("הוספת הערה", "Add a note")}</summary>        <label>
          {t("הערות", "Notes")}
          <textarea
            name="notes"
            rows={3}
            maxLength={10000}
            defaultValue={record?.notes ?? draft?.notes ?? ""}
          />
        </label></details>
        {error && (
          <p role="alert" className="error-message">
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
