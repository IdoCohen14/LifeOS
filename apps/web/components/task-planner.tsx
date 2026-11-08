"use client";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { CalendarClock, ArrowUpLeft, Check } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { DEFAULT_PLANNING, planningDefaults, type PlanningPreferences } from "@/lib/planning-preferences";
import { dayKey, shiftDay } from "@/lib/dates";
import type { CalendarEvent, Settings, Task, Translate } from "@/lib/types";
import { WeekdayPicker } from "./weekday-picker";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";

type Block = Pick<CalendarEvent, "id" | "title" | "start" | "end" | "all_day">;
type Plan = {
  proposal: { id: string; kind: "event"; payload: Omit<Block, "id"> } | null;
  existing?: Block | null;
  reason?: string;
  overdue?: boolean;
  deadline_ignored?: boolean;
  daily_limit_minutes?: number;
  stale_sources?: string[];
};

export function TaskPlanner({
  tasks,
  settings,
  today,
  csrf,
  t,
  onChanged,
  onUnauthorized,
  onDay,
  compact = false,
  disabled = false,
}: {
  tasks: Task[];
  settings: Settings;
  today: string;
  csrf: string;
  t: Translate;
  onChanged: () => Promise<void>;
  onUnauthorized: () => void;
  onDay: (day: string) => void;
  compact?: boolean;
  disabled?: boolean;
}) {
  const [defaults, setDefaults] = useState(DEFAULT_PLANNING);
  const [preferenceError, setPreferenceError] = useState(false);
  const [preferencesUsed, setPreferencesUsed] = useState(false);
  const generation = useRef(0);
  async function openPlanner() {
    const current = ++generation.current;
    setBusy(true); setPreferenceError(false);
    try {
      const value = await api<PlanningPreferences>("planning/preferences");
      if (generation.current !== current) return;
      setDefaults(planningDefaults(value)); setPreferencesUsed(value.enabled);
    } catch (error) {
      if (generation.current !== current) return;
      if (error instanceof ApiError && error.status === 401) { onUnauthorized(); return; }
      setDefaults(DEFAULT_PLANNING); setPreferencesUsed(false); setPreferenceError(true);
    } finally { if (generation.current === current) setBusy(false); }
    if (generation.current === current) setOpen(true);
  }
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [taskId, setTaskId] = useState(tasks[0]?.id ?? "");
  const [query, setQuery] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const options = useMemo(
    () =>
      tasks
        .filter(
          (task) =>
            !task.completed &&
            task.title.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
        )
        .slice(0, 200),
    [tasks, query],
  );
  const selected = options.find((task) => task.id === taskId);
  const locked = !!plan?.proposal || !!plan?.existing || saved;
  const format = (instant: string) =>
    new Intl.DateTimeFormat(settings.language, {
      timeZone: settings.timezone,
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZoneName: "shortOffset",
    }).format(new Date(instant));
  function failed(error: unknown) {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
    setError(
      error instanceof ApiError
        ? error.status === 404
          ? "expired"
          : error.status === 409
            ? "changed"
            : error.status === 422
              ? "invalid"
              : error.status === 429
                ? "limit"
                : "unavailable"
        : "unavailable",
    );
  }
  async function cancelPending() {
    if (plan?.proposal && !saved) {
      try {
        await api(
          `planning/proposals/${plan.proposal.id}`,
          "DELETE",
          undefined,
          csrf,
        );
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) onUnauthorized();
      }
    }
  }
  function close() {
    if (busy && !saved) return;
    void cancelPending();
    generation.current += 1;
    setBusy(false);
    setOpen(false);
    setPlan(null);
    setSaved(false);
    setError("");
  }
  async function reset() {
    setBusy(true);
    await cancelPending();
    setPlan(null);
    setSaved(false);
    setError("");
    setBusy(false);
  }
  async function propose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setPlan(null);
    setSaved(false);
    try {
      setPlan(
        await api<Plan>(
          "planning/propose",
          "POST",
          {
            task_id: selected.id,
            duration: Number(form.get("duration")),
            day: String(form.get("day")),
            days: Number(form.get("days")),
            weekdays: form.getAll("weekdays").map(Number),
            window_start: String(form.get("window_start")),
            window_end: String(form.get("window_end")),
            allow_after_due: form.has("allow_after_due"),
            daily_limit_minutes: String(form.get("daily_limit_minutes")??"").trim()?Number(form.get("daily_limit_minutes")):null,
          },
          csrf,
        ),
      );
    } catch (error) {
      failed(error);
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    if (!plan?.proposal || saved || busy) return;
    const current = generation.current;
    setBusy(true);
    setError("");
    try {
      await api("assistant/confirm", "POST", { id: plan.proposal.id }, csrf);
      if (generation.current !== current) return;
      setSaved(true);
      try {
        await onChanged();
      } catch {
        if (generation.current === current) setError("refresh");
      }
    } catch (error) {
      if (generation.current === current) failed(error);
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }
  const block = plan?.proposal?.payload ?? plan?.existing;
  if (!tasks.some((task) => !task.completed)) return null;
  return (
    <>
      {compact ? <Button variant="secondary" disabled={busy || disabled} aria-label={`${t("הקצאת זמן", "Plan time")}: ${tasks[0]?.title}`} onClick={()=>void openPlanner()}><CalendarClock size={15} aria-hidden="true"/>{t("הקצאת זמן", "Plan time")}</Button> : <section className="panel planner-entry">
        <div className="heading-with-icon">
          <CalendarClock size={22} aria-hidden="true" />
          <div>
            <h2>
              {t("להקדיש זמן למשימה חשובה", "Make time for an important task")}
            </h2>
            <p className="field-help" dir="auto">
              {t(
                "בחרו משימה ומשך, ונציע משבצת לפי היומן השמור.",
                "Choose a task and duration for a time block based on your saved calendar.",
              )}
            </p>
          </div>
        </div>
        <Button variant="secondary" disabled={busy || disabled} onClick={() => void openPlanner()}>
          {t("מציאת משבצת זמן", "Find a time block")}
          <ArrowUpLeft size={15} aria-hidden="true" />
        </Button>
      </section>}
      {open && (
        <Modal
          open
          onClose={close}
          title={t("תכנון זמן למשימה", "Plan time for a task")}
          description={t(
            "הצעה לפי היומן השמור. שום אירוע לא יישמר לפני אישורך.",
            "A suggestion from your saved calendar. No event is saved before your confirmation.",
          )}
          closeLabel={t("סגירה", "Close")}
        >
          {preferenceError && <p role="status" className="field-help">{t("ההעדפות השמורות אינן זמינות. הוצגו ברירות המחדל הרגילות; בדקו את המשך והשעות לפני ההצעה.", "Saved preferences are unavailable. Built-in defaults are shown; review duration and hours before proposing.")}</p>}
          {preferencesUsed && <p className="field-help">{t("מולאו ההעדפות ששמרת. אפשר לשנות אותן עבור הצעה זו.", "Your saved preferences are filled in. You can change them for this proposal.")}</p>}
          <form className="form-stack" onSubmit={propose}>
            <fieldset className="planner-fields" disabled={busy || locked}>
              {tasks.length > 20 && (
                <label>
                  {t("חיפוש משימה", "Search tasks")}
                  <input
                    type="search"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </label>
              )}
              <label>
                {t("משימה לתכנון", "Task to plan")}
                <select
                  aria-label={t("משימה לתכנון", "Task to plan")}
                  value={selected ? taskId : ""}
                  onChange={(event) => setTaskId(event.target.value)}
                >
                  <option value="" disabled>
                    {t("בחרו משימה", "Choose a task")}
                  </option>
                  {options.map((task) => (
                    <option key={task.id} value={task.id}>
                      {task.title}
                    </option>
                  ))}
                </select>
              </label>
              {tasks.length > 200 && (
                <p className="field-help">
                  {t(
                    "מוצגות עד 200 תוצאות; חפשו לפי כותרת כדי למצוא משימות נוספות.",
                    "Showing up to 200 results; search by title to find other tasks.",
                  )}
                </p>
              )}
              <div className="form-grid">
                <label>
                  {t("משך בדקות", "Duration in minutes")}
                  <input
                    type="number"
                    name="duration"
                    aria-label={t("משך בדקות", "Duration in minutes")}
                    min={5}
                    max={240}
                    step={5}
                    defaultValue={defaults.duration}
                    required
                  />
                </label>
                <label>
                  {t("מתאריך", "Starting date")}
                  <input
                    type="date"
                    name="day"
                    required
                    defaultValue={today}
                    min={today}
                    max={shiftDay(today, 30)}
                  />
                </label>
              </div>
              <label>
                {t("טווח חיפוש", "Search period")}
                <select
                  name="days"
                  aria-label={t("טווח חיפוש", "Search period")}
                  defaultValue={String(defaults.days)}
                >
                  {Array.from({ length: 7 }, (_, index) => index + 1).map(
                    (value) => (
                      <option key={value} value={value}>
                        {value === 1
                          ? t("יום אחד", "One day")
                          : t(
                              `${value} ימים רצופים`,
                              `${value} consecutive days`,
                            )}
                      </option>
                    ),
                  )}
                </select>
              </label>
              <WeekdayPicker defaultValue={defaults.weekdays} t={t} />
              <p className="field-help">{t("בחרו לפחות יום אחד. הימים מסננים את הטווח שבחרתם; טווח החיפוש אינו מתארך.", "Choose at least one weekday. These days filter the selected period; the search does not extend beyond it.")}</p>
              <details className="notification-preferences">
                <summary>{t("אפשרויות תכנון", "Planning options")}</summary>
                <div className="form-grid">
                  <label>
                    {t("תחילת חלון התכנון", "Planning window start")}
                    <input
                      type="time"
                      name="window_start"
                      required
                      defaultValue={defaults.window_start}
                    />
                  </label>
                  <label>
                    {t("סיום חלון התכנון", "Planning window end")}
                    <input
                      type="time"
                      name="window_end"
                      required
                      defaultValue={defaults.window_end}
                    />
                  </label>
                </div>
                <label>{t("תקרת דקות מתוזמנות ביום (ריק = ללא תקרה)","Daily scheduled-minute cap (blank = no cap)")}<input type="number" name="daily_limit_minutes" min={15} max={1440} step={15} defaultValue={defaults.daily_limit_minutes??""}/></label>
                <p className="field-help">{t("נספר הזמן של אירועים עם שעות ביומן לאורך כל היום, גם מחוץ לחלון החיפוש; חפיפות נספרות פעם אחת. מועדי הגשה ומשך אירועי יום שלם אינם נספרים כזמן עבודה. זו אינה הערכה של הלמידה בפועל.","Counts timed calendar occupancy across the whole day, including outside the search window; overlaps count once. Due dates and all-day duration are not counted as work time. This does not estimate actual study effort.")}</p>
                <label className="notification-check">
                  <input type="checkbox" name="allow_after_due" />
                  {t(
                    "לאפשר גם אחרי מועד המשימה",
                    "Allow time after the task deadline",
                  )}
                </label>
              </details>
            </fieldset>
            {!locked && (
              <Button type="submit" disabled={busy || !selected}>
                {busy
                  ? t("מחפש…", "Finding a slot…")
                  : t("הצעת זמן", "Suggest a time")}
              </Button>
            )}
          </form>
          {plan?.reason === "no_slot" && (
            <p role="status" className="field-help">
              {t(
                "לא נמצאה משבצת מתאימה בחלון ובטווח שבחרת. אפשר לשנות יום, משך או את אפשרויות התכנון.",
                "No suitable block was found in your chosen window. Try another date, duration or planning options.",
              )}
            </p>
          )}
          {block && (
            <div className="planner-proposal">
              {plan?.daily_limit_minutes&&<p className="field-help">{t(`תקרה שנבחרה: ${plan.daily_limit_minutes} דקות מתוזמנות ביום.`,`Selected cap: ${plan.daily_limit_minutes} scheduled minutes per day.`)}</p>}
              <strong dir="auto">{block.title}</strong>
              <p>
                {format(block.start)} — {format(block.end)}
              </p>
              <p className="field-help">{settings.timezone}</p>
              {plan?.existing && (
                <p role="status">
                  {t(
                    "כבר מוקצה למשימה זמן עתידי ביומן.",
                    "This task already has a future calendar block.",
                  )}
                </p>
              )}
              {plan?.overdue && (
                <p className="field-help">
                  {t(
                    "מועד המשימה עבר. הקצאת הזמן אינה משנה את המועד המקורי.",
                    "The task is overdue. Allocating time does not change its original deadline.",
                  )}
                </p>
              )}
              {plan?.deadline_ignored && (
                <p className="field-help">
                  {t(
                    "בחרת לאפשר תכנון גם אחרי המועד. יש לבדוק את ההצעה בהתאם.",
                    "You allowed planning after the deadline. Review this proposal accordingly.",
                  )}
                </p>
              )}
              {!!plan?.stale_sources?.length && (
                <p role="status" className="field-help">
                  {t(
                    "ייתכן שהמידע המיובא לא מעודכן; בדקו את יומני המקור לפני האישור",
                    "Imported data may be outdated; check source calendars before confirming",
                  )}
                  : {plan.stale_sources.join(", ")}
                </p>
              )}
              <p className="field-help">
                {t(
                  "המשבצת אינה מתנגשת בפריטים הידועים ביומן השמור. זמינות בפועל עשויה להשתנות. השמירה היא ביומן האישי של LifeOS בלבד.",
                  "This block does not overlap known saved calendar items. Actual availability may differ. Saving creates a personal LifeOS event only.",
                )}
              </p>
              {saved ? (
                <p className="assistant-saved" role="status">
                  <Check size={16} aria-hidden="true" />
                  {t(
                    "נשמר ביומן. המשימה נשארת פתוחה.",
                    "Saved to your calendar. The task stays open.",
                  )}
                </p>
              ) : (
                plan?.proposal && (
                  <div className="form-actions">
                    <Button disabled={busy} onClick={() => void confirm()}>
                      {t("אישור ושמירה ביומן", "Confirm and save to calendar")}
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={busy}
                      onClick={() => void reset()}
                    >
                      {t("שינוי הבקשה", "Change request")}
                    </Button>
                  </div>
                )
              )}
              {(saved || plan?.existing) && (
                <Button
                  variant="secondary"
                  onClick={() => {
                    close();
                    onDay(
                      block.all_day
                        ? block.start
                        : dayKey(new Date(block.start), settings.timezone),
                    );
                  }}
                >
                  {t("פתיחה ביומן", "Open in calendar")}
                </Button>
              )}
            </div>
          )}
          {error && (
            <p role="alert" className="error-message">
              {error === "changed"
                ? t(
                    "המשימה או היומן השתנו, או שכבר הוקצה זמן למשימה. יש לבקש הצעה חדשה.",
                    "The task/calendar changed, or the task already has a block. Request a fresh proposal.",
                  )
                : error === "expired"
                  ? t(
                      "ההצעה פגה או בוטלה. יש לבקש הצעה חדשה.",
                      "The proposal expired or was cancelled. Request a new one.",
                    )
                  : error === "invalid"
                    ? t(
                        "יש לבדוק את התאריך, המשך וחלון השעות. שעות לא קיימות או דו־משמעיות אינן מתקבלות.",
                        "Check the date, duration and time window. Missing or ambiguous local times are rejected.",
                      )
                    : error === "limit"
                      ? t(
                          "יש יותר מדי הצעות פתוחות. סגרו הצעות קיימות או המתינו לפקיעתן.",
                          "Too many proposals are open. Close existing proposals or wait for expiry.",
                        )
                      : error === "refresh"
                        ? t(
                            "נשמר, אך יש לרענן את התצוגה.",
                            "Saved, but the view needs refreshing.",
                          )
                        : t(
                            "לא ניתן להכין או לשמור את ההצעה כרגע. לא תתבצע שמירה בלי אישור.",
                            "Could not prepare or save the proposal. Nothing is saved without confirmation.",
                          )}
            </p>
          )}
        </Modal>
      )}
    </>
  );
}
