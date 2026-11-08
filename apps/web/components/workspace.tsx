"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowUpLeft,
  CalendarDays,
  ChevronLeft,
  GraduationCap,
  LayoutDashboard,
  ListTodo,
  LoaderCircle,
  LogOut,
  Mail,
  Plus,
  Settings2,
  ShieldCheck,
  Compass,
  MessageCircle,
  Sun,
  Unplug,
  X,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Course } from "@/lib/academic";
import { AccountAccessRecovery } from "./account-access";
import { calendarDayParameter, dayKey, eventOnDay, formatDay } from "@/lib/dates";
import type {
  CalendarEvent,
  Settings,
  Task,
  Translate,
  View,
} from "@/lib/types";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";
import { Agenda } from "./agenda";
import { TaskList } from "./task-list";
import { UpcomingEvent } from "./day-dashboard";
import { HomeFocusTasks } from "./home-focus-tasks";
import { DayOverviewRail } from "./day-overview-rail";
import { PersonalUpdates } from "./personal-updates";
import { ProviderHealth, sourceOutdated } from "./provider-health";
import { CalendarView } from "./calendar-view";
import { PlanningBriefing } from "./planning-briefing";
import { TaskPlanner } from "./task-planner";
import { AcademicSnapshot } from "./academic-snapshot";
import { WeeklyReview } from "./weekly-review";
import { SettingsView } from "./settings-view";
import { RecurringEvents } from "./recurring-events";
import { RecordForm, type Editor } from "./record-form";
import { Reauthenticate } from "./reauthenticate";
import { AcademicView } from "./academic-view";
import { AssistantChat } from "./assistant-chat";
import { AssistantRequests } from "./assistant-requests";
import { PlanningNudge } from "./planning-nudge";
import type { AssistantChatHandle, TrackedRequest } from "@/lib/assistant-requests";
import { RecommendationsPanel, type RecommendationFeed } from "./recommendations-panel";
import { MoodleUpdates } from "./moodle-updates";
import { ClassTimetable } from "./class-timetable";
import { isClassEvent } from "@/lib/class-schedule";
import { DailyMail } from "./daily-mail";
import { NotificationCenter, type NotificationFeed, type NotificationItem } from "./notification-center";
import type { MoodleStatus } from "./moodle-settings";
import type { GmailStatus } from "./gmail-settings";
import type { GoogleCalendarStatus } from "@/lib/google-calendar";

const defaults: Settings = {
  display_name: "",
  language: "he",
  theme: "dark",
  timezone: "Asia/Jerusalem",
};
const priorities = { high: 0, medium: 1, low: 2 };
const viewIcons = {
  dashboard: LayoutDashboard,
  tasks: ListTodo,
  calendar: CalendarDays,
  settings: Settings2,
  academic: GraduationCap,
  timetable: CalendarDays,
};

export function Login({ onLogin, accountMode = false, registrationOpen = true }: {
  onLogin: (password: string, login?: string, register?: boolean) => Promise<void>;
  accountMode?: boolean;
  registrationOpen?: boolean;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [register, setRegister] = useState(false);
  const [recoverAccess, setRecoverAccess] = useState(false);
  return (
    <main className="login-page" dir="rtl">
      <div className="login-decoration" aria-hidden="true">
        <div className="orbit orbit-one" />
        <div className="orbit orbit-two" />
        <div className="orbit orbit-three" />
        <span className="orbit-dot" />
      </div>
      <section className="login-card">
        <div className="brand">
          <span className="brand-mark">
            <Compass size={23} aria-hidden="true" />
          </span>
          <span translate="no">
            Life<span className="accent">OS</span>
          </span>
        </div>
        <span className="local-badge">
          <span />
          {accountMode ? "המרחב האישי שלך" : "המרחב האישי המקומי שלך"}
        </span>
        <h1>
          פחות עומס.
          <br />
          יותר מקום לחיים.
        </h1>
        <p className="muted">
          {accountMode ? "המשימות, היומן והיום שלך — במקום אחד." : "המשימות, היומן והיום שלך — במקום אחד, במחשב שלך."}
        </p>
        {recoverAccess ? <AccountAccessRecovery t={(he)=>he} onBack={()=>setRecoverAccess(false)} /> : <><form
          className="form-stack"
          onSubmit={async (e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            if (register && data.get("password") !== data.get("confirm_password")) {
              setError("הסיסמאות אינן תואמות.");
              return;
            }
            setBusy(true);
            setError("");
            try {
              await onLogin(String(data.get("password")), accountMode ? String(data.get("login")).trim() : undefined, accountMode && register);
            } catch (error) {
              setError(
                error instanceof ApiError && error.status === 401
                  ? "פרטי הכניסה שגויים. נסו שוב."
                  : error instanceof ApiError && error.status === 429
                    ? "יותר מדי ניסיונות. נסו שוב בעוד דקה."
                    : "לא ניתן להתחבר. ודאו שהשרת המקומי פועל ושההגדרה הראשונית הושלמה.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          {accountMode && <label>שם משתמש<input name="login" required maxLength={254} autoComplete="username" dir="ltr" /></label>}
          <label>
            הסיסמה שלך
            <input
              name="password"
              type="password"
              required
              minLength={8}
              maxLength={1024}
              autoComplete={register ? "new-password" : "current-password"}
              dir="ltr"
            />
          </label>
          {register && <label>אימות סיסמה<input name="confirm_password" type="password" required minLength={8} maxLength={1024} autoComplete="new-password" dir="ltr" /></label>}
          <Button type="submit" disabled={busy}>
            {busy ? (
              <LoaderCircle className="spin" aria-hidden="true" size={18} />
            ) : null}
            {busy ? "מתחבר…" : register ? "צור חשבון" : "כניסה למרחב שלך"}
            <ChevronLeft size={17} aria-hidden="true" />
          </Button>
          {error && (
            <p className="error-message" role="alert">
              {error}
            </p>
          )}
        </form>
        {accountMode && registrationOpen && <Button variant="secondary" disabled={busy} onClick={() => { setRegister(!register); setError(""); }}>{register ? "כבר יש לי חשבון" : "יצירת חשבון חדש"}</Button>}
        {accountMode && !registrationOpen && <p className="field-help">פיילוט פרטי — ההרשמה סגורה</p>}
        {accountMode && !register && <Button variant="ghost" disabled={busy} onClick={()=>setRecoverAccess(true)}>שכחתם סיסמה? שחזור באמצעות מפתח</Button>}
        {accountMode && register && <p className="field-help">לאחר הכניסה אפשר ליצור מפתח שחזור אישי בהגדרות.</p>}
        </>}
        <p className="login-security">
          <ShieldCheck size={16} aria-hidden="true" />
          {accountMode ? "גישה אישית מוגנת · המידע בחשבון שלך" : "גישה מקומית בלבד · ללא שירות ענן"}
        </p>
        {!accountMode && <details className="setup-help">
          <summary>כניסה ראשונה?</summary>
          <p>
            הפעילו את <bdi>scripts/run.py</bdi> כדי לבחור סיסמה ולהפעיל את
            LifeOS. המידע נשמר בתיקיית הנתונים האישית של LifeOS במחשב שלכם.
          </p>
        </details>}
      </section>
    </main>
  );
}

export function Workspace() {
  const router = useRouter();
  const search = useSearchParams();
  const rawView = search.get("view");
  const view: View =
    rawView === "tasks" ||
    rawView === "calendar" ||
    rawView === "settings" ||
    rawView === "academic" || rawView === "timetable"
      ? rawView
      : "dashboard";
  const [state, setState] = useState<"loading" | "login" | "ready" | "error">(
    "loading",
  );
  const [accountMode, setAccountMode] = useState(false);
  const [registrationOpen,setRegistrationOpen] = useState(true);
  const [accountLogin, setAccountLogin] = useState("");
  const accountModeRef = useRef(false);
  const assistantRef = useRef<AssistantChatHandle>(null);
  const [requestRevision, setRequestRevision] = useState(0);
  const [planningRevision, setPlanningRevision] = useState(0);
  const accountIdentity = useRef<{ account_id?: string; csrf: string } | null>(null);
  const previousView = useRef(view);
  useEffect(() => {
    const changed = previousView.current !== view;
    previousView.current = view;
    if (changed && state === "ready") {
      document.getElementById("main-content")?.focus({ preventScroll: true });
    }
  }, [view, state]);
  const [settings, setSettings] = useState(defaults);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [notifications, setNotifications] = useState<NotificationFeed | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationFeed | null>(null);
  const [moodle, setMoodle] = useState<MoodleStatus | null>(null);
  const [braude, setBraude] = useState<MoodleStatus | null>(null);
  const [gmail, setGmail] = useState<GmailStatus | null>(null);
  const [google, setGoogle] = useState<GoogleCalendarStatus | null>(null);
  const [csrf, setCsrf] = useState("");
  const [notice, setNotice] = useState("");
  const [stale, setStale] = useState(false);
  const [reauthenticate, setReauthenticate] = useState(false);
  const requireReauthentication = useCallback(
    () => setReauthenticate(true),
    [setReauthenticate],
  );
  const [editor, setEditor] = useState<Editor | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{
    kind: "task" | "event";
    record: Task | CalendarEvent;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<"open" | "all" | "completed">("open");
  const [now, setNow] = useState(() => new Date());
  const t: Translate = useCallback((he: string, en: string) => (settings.language === "he" ? he : en), [settings.language]);
  const today = dayKey(now, settings.timezone);
  const titles = {
    dashboard: t("היום שלי", "My day"),
    tasks: t("המשימות שלי", "My tasks"),
    calendar: t("היומן שלי", "My calendar"),
    settings: t("הגדרות", "Settings"),
    academic: t("הלימודים שלי", "My studies"),
    timetable: t("מערכת השעות שלי", "My timetable"),
  };
  const refreshSequence = useRef(0);
  const refresh = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    try {
      const identity = accountModeRef.current ? await api<{ account_id: string; csrf: string }>("session") : null;
      if (sequence !== refreshSequence.current) return;
      if (identity && accountIdentity.current && (identity.account_id !== accountIdentity.current.account_id || identity.csrf !== accountIdentity.current.csrf)) {
        window.location.reload();
        return;
      }
      const snapshot = await Promise.all([
        api<Task[]>("tasks"),
        api<CalendarEvent[]>("events"),
        api<Settings>("settings"),
        api<CalendarEvent[]>("academic/calendar"),
        api<CalendarEvent[]>("integrations/google/events"),
        api<GoogleCalendarStatus>("integrations/google/status"),
        api<GmailStatus>("integrations/gmail/status"),
        api<CalendarEvent[]>("integrations/moodle/events"),
        api<CalendarEvent[]>("integrations/braude/events").catch(error => { if (error instanceof ApiError && error.status === 404) return []; throw error; }),
        api<MoodleStatus>("integrations/moodle/status"),
        api<MoodleStatus>("integrations/braude/status").catch(error => { if (error instanceof ApiError && error.status === 404) return null; throw error; }),
        api<RecommendationFeed>("recommendations").catch(() => null),
        api<NotificationFeed>("notifications").catch(() => null),
        api<Course[]>("academic/courses").catch(error => { if (error instanceof ApiError && error.status === 401) throw error; return []; }),
      ]);
      if (!snapshot || sequence !== refreshSequence.current) return;
      if (identity) {
        const current = await api<{ account_id: string; csrf: string }>("session");
        if (sequence !== refreshSequence.current) return;
        if (current.account_id !== identity.account_id || current.csrf !== identity.csrf) {
          window.location.reload();
          return;
        }
      }
      const [
        nextTasks,
        nextEvents,
        nextSettings,
        academicEvents,
        googleEvents,
        googleStatus,
        gmailStatus,
        moodleEvents,
        braudeEvents,
        moodleStatus,
        braudeStatus,
        recommendationFeed,
        notificationFeed,
        nextCourses,
      ] = snapshot;
      setTasks(nextTasks.filter(task => task.academic_kind !== "exam"));
      setPlanningRevision(sequence);
      setEvents([...nextEvents, ...academicEvents, ...googleEvents, ...moodleEvents, ...braudeEvents]);
      setGoogle(googleStatus);
      setGmail(gmailStatus);
      setMoodle(moodleStatus);
      setBraude(braudeStatus);
      setRecommendations(recommendationFeed);
      setNotifications(notificationFeed);
      setSettings(nextSettings);
      setCourses(nextCourses);
      setStale(false);
    } catch (error) {
      if (sequence !== refreshSequence.current) return;
      setStale(true);
      throw error;
    }
  }, []);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const mode = await api<{ account_mode: boolean; registration_open?: boolean }>("mode");
        setRegistrationOpen(mode.registration_open !== false);
        if (!active) return;
        accountModeRef.current = mode.account_mode;
        setAccountMode(mode.account_mode);
        const session = await api<{ csrf: string; account_id?: string; login?: string }>("session");
        if (!active) return;
        accountIdentity.current = session;
        setAccountLogin(session.login || "");
        setCsrf(session.csrf);
        await refresh();
        if (active) setState("ready");
      } catch (error) {
        if (active)
          setState(
            error instanceof ApiError && error.status === 401
              ? "login"
              : "error",
          );
      }
    })();
    return () => {
      active = false;
      refreshSequence.current += 1;
    };
  }, [refresh]);
  useEffect(() => {
    if (state !== "ready") return;
    const update = () => {
      void refresh().catch(() => {});
    };
    const timer = setInterval(update, 60000);
    window.addEventListener("focus", update);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", update);
    };
  }, [state, refresh]);
  useEffect(() => {
    document.documentElement.dir = settings.language === "he" ? "rtl" : "ltr";
    document.documentElement.lang = settings.language;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme =
        settings.theme === "system"
          ? media.matches
            ? "dark"
            : "light"
          : settings.theme;
      document.querySelector('meta[name="theme-color"]')?.setAttribute(
        "content", document.documentElement.dataset.theme === "light" ? "#f3f4f6" : "#151719",
      );
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [settings.language, settings.theme]);
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60000);
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production")
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    return () => clearInterval(timer);
  }, []);

  async function login(password: string, loginName?: string, register = false) {
    if (accountMode && register) await api("accounts/register", "POST", { login: loginName, password });
    const session = await api<{ csrf: string }>("session", "POST", {
      password,
      ...(accountMode ? { login: loginName } : {}),
    });
    if (accountMode) { window.location.replace(register ? "/?view=settings" : window.location.href); return; }
    setCsrf(session.csrf);
    await refresh();
    setState("ready");
  }
  async function mutate(path: string, method: string, body?: unknown) {
    try {
      await api(path, method, body, csrf);
      try {
        await refresh();
      } catch {
        // The write succeeded. Do not invite a duplicate create by reporting a failed save.
        // Shared refresh already marks the current snapshot stale.
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setReauthenticate(true);
      }
      throw error;
    }
  }
  async function toggle(task: Task) {
    setBusy(true);
    try {
      await mutate(`tasks/${task.id}`, "PUT", {
        ...task,
        completed: !task.completed,
      });
      setNotice(
        task.completed
          ? t("המשימה נפתחה מחדש.", "Task reopened.")
          : t("עוד צעד הושלם.", "One more step done."),
      );
    } catch {
      setNotice(t("העדכון נכשל. נסו שוב.", "Update failed. Retry."));
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!pendingDelete) return;
    setBusy(true);
    try {
      await mutate(
        `${pendingDelete.kind === "task" ? "tasks" : "events"}/${pendingDelete.record.id}`,
        "DELETE",
      );
      setPendingDelete(null);
      setNotice(t("הפריט נמחק.", "Item deleted."));
    } catch {
      setNotice(t("המחיקה נכשלה. נסו שוב.", "Delete failed. Retry."));
    } finally {
      setBusy(false);
    }
  }
  function navigate(next: View) {
    router.push(next === "dashboard" ? "/" : `/?view=${next}`);
    setNotice("");
  }
  const sorted = [...tasks].sort(
    (a, b) =>
      Number(a.completed) - Number(b.completed) ||
      priorities[a.priority] - priorities[b.priority] ||
      (a.due ?? "9999").localeCompare(b.due ?? "9999"),
  );
  const openTasks = sorted.filter((task) => !task.completed);
  const todayEvents = events.filter((event) =>
    eventOnDay(event, today, settings.timezone),
  );
  const taskProps = {
    settings,
    today,
    now,
    t,
    onEdit: (task: Task) =>
      task.academic_course_id
        ? router.push(`/?view=academic&course=${task.academic_course_id}`)
        : setEditor({ kind: "task", record: task }),
    onToggle: toggle,
    onDelete: (task: Task) => setPendingDelete({ kind: "task", record: task }),
    onAdd: () => setEditor({ kind: "task" }),
    busy,
  };
  const discussUpdate = async (item: NotificationItem) => {
    const reference = item.request_id
      ? await api<TrackedRequest>(`assistant/requests/${item.request_id}`)
      : await api<TrackedRequest>("assistant/requests", "POST", { notice_id: item.id }, csrf);
    const request = await api<TrackedRequest>(`assistant/requests/${reference.id}`);
    setRequestRevision(value => value + 1);
    if (!assistantRef.current?.openRequest(request)) throw new Error("Assistant busy");
  };
  const openTrackedRequest = async (item: TrackedRequest) => {
    try {
      const fresh = await api<TrackedRequest>(`assistant/requests/${item.id}`);
      if (!assistantRef.current?.openRequest(fresh)) setNotice(t("העוזר עדיין משלים את הבקשה הקודמת.", "The assistant is finishing the previous request."));
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) requireReauthentication();
      setNotice(t("לא ניתן לפתוח את הבקשה כרגע. רעננו את הרשימה.", "Could not open this request. Refresh the list."));
    }
  };
  const openUpdate = (item: NotificationItem) => {
    if (item.request_id) { void discussUpdate(item).catch(() => setNotice(t("לא ניתן לפתוח את הבקשה כרגע.", "Could not open the request."))); return; }
    if (item.kind === "new_mail") { router.push("/#my-mail"); return; }
    if (item.lesson && item.start) { router.push(`/?view=timetable&day=${dayKey(new Date(item.start), settings.timezone)}`); return; }
    if (item.briefing) { router.push(item.kind === "weekly_briefing" ? "/?briefing=week" : "/?briefing=day"); return; }
    const task = tasks.find(task => item.source_ids.includes(task.id));
    if (task?.academic_kind === "exam" && task.due) router.push(`/?view=calendar&day=${task.due.length === 10 ? task.due : dayKey(new Date(task.due), settings.timezone)}`);
    else if (item.target === "tasks" && task) taskProps.onEdit(task);
    else if (item.start) router.push(`/?view=calendar&day=${item.start.length === 10 ? item.start : dayKey(new Date(item.start), settings.timezone)}`);
    else navigate(item.target);
  };
  const readUpdates = async (ids: string[]) => { setNotifications(await api<NotificationFeed>("notifications/read", "POST", { ids }, csrf)); };
  const actOnUpdate = async (action: import("./notification-center").NotificationAction) => { setNotifications(await api<NotificationFeed>("notifications/action", "POST", action, csrf)); };
  const refreshUpdates = async () => { setNotifications(await api<NotificationFeed>("notifications")); };
  const agendaProps = {
    allEvents: events,
    settings,
    t,
    onEdit: (event: CalendarEvent) =>
      (event.source === "google" || event.source === "moodle" || event.source === "braude")
        ? setNotice(
            t(
              "אירוע מיובא לקריאה בלבד. השתמשו בקישור המקור.",
              "Imported event is read-only. Use its source link.",
            ),
          )
        : event.course_id
          ? router.push(`/?view=academic&course=${event.course_id}`)
          : setEditor({ kind: "event", record: event }),
    onDelete: (event: CalendarEvent) =>
      setPendingDelete({ kind: "event", record: event }),
    onAdd: () => setEditor({ kind: "event", day: today }),
    busy,
  };

  if (state === "loading")
    return (
      <main className="boot">
        <LoaderCircle className="spin" size={26} aria-hidden="true" />
        <p>טוען את המרחב שלך…</p>
      </main>
    );
  if (state === "login") return <Login accountMode={accountMode} registrationOpen={registrationOpen} onLogin={login} />;
  if (state === "error")
    return (
      <main className="boot">
        <Unplug size={32} aria-hidden="true" />
        <h1>השרת המקומי לא זמין</h1>
        <p>הפעילו את LifeOS ונסו שוב. המידע השמור נשאר במחשב.</p>
        <Button onClick={() => window.location.reload()}>ניסיון נוסף</Button>
      </main>
    );
  return (
    <div className={`app-shell calm-shell view-${view}`}>
      <a className="skip-link" href="#main-content">
        {t("דילוג לתוכן", "Skip to content")}
      </a>
      <aside className="sidebar">
        <Link href="/" className="brand">
          <span className="brand-mark">
            <Compass size={22} aria-hidden="true" />
          </span>
          <span translate="no">
            Life<span className="accent">OS</span>
          </span>
        </Link>
        <p className="sidebar-caption">
          {t("המרחב שלי", "My workspace")}
        </p>
        <nav
          aria-label={t("ניווט ראשי", "Main navigation")}
          className="main-nav"
        >
          {(["dashboard", "academic", "tasks", "calendar"] as const).map(
            (v) => {
              const Icon = viewIcons[v];
              return (
                <Link
                  key={v}
                  href={v === "dashboard" ? "/" : `/?view=${v}`}
                  aria-current={view === v || (v === "academic" && view === "timetable") ? "page" : undefined}
                >
                  <Icon size={19} aria-hidden="true" />
                  <span className="nav-full-label">{titles[v]}</span><span className="nav-short-label">{{dashboard:t("היום", "Today"),timetable:t("שיעורים", "Classes"),calendar:t("יומן", "Calendar"),tasks:t("משימות", "Tasks"),academic:t("לימודים", "Study")}[v]}</span>
                  {v === "tasks" && openTasks.length > 0 && (
                    <span className="nav-count">{openTasks.length}</span>
                  )}
                </Link>
              );
            },
          )}
        </nav>
        <div className="sidebar-section sidebar-quick-actions">
          <span className="sidebar-section-label">{t("כלים אישיים", "Personal tools")}</span>
          <Link className="sidebar-action" href="/#my-mail"><Mail size={19} aria-hidden="true"/><span>{t("פתיחת המיילים שלי", "Open my mail")}</span></Link>
          <button className="sidebar-action" type="button" onClick={()=>document.getElementById("lifeos-assistant-launcher")?.click()}><MessageCircle size={19} aria-hidden="true"/><span>{t("פתיחת העוזר", "Open assistant")}</span></button>
        </div>
        <div className="sidebar-bottom">
          <div className="local-status">
            <span className="status-dot" />
            <div>
              <strong>{t("נשמר במחשב שלך", "Stored on your computer")}</strong>
              <span>
                {t("המרחב שלך. המידע שלך.", "Your space. Your data.")}
              </span>
            </div>
            <ShieldCheck size={16} aria-hidden="true" />
          </div>
          <Link
            className={`settings-link ${view === "settings" ? "active" : ""}`}
            href="/?view=settings"
            aria-current={view === "settings" ? "page" : undefined}
          >
            <Settings2 size={19} aria-hidden="true" />
            {titles.settings}
          </Link>
          <button
            className="profile-button"
            onClick={async () => {
              try {
                await api("session", "DELETE", undefined, csrf);
                refreshSequence.current += 1;
                setTasks([]);
                setEvents([]);
                setCourses([]);
                setSettings(defaults);
                setState("login");
                if (accountMode) window.location.reload();
              } catch {
                setNotice(
                  t("היציאה נכשלה. נסו שוב.", "Could not sign out. Retry."),
                );
              }
            }}
          >
            <span className="avatar">
              {settings.display_name.slice(0, 1) || t("א", "L")}
            </span>
            <span>
              <strong>
                {settings.display_name || t("המרחב שלי", "My workspace")}
              </strong>
              <small>{t("חשבון מקומי", "Local account")}</small>
            </span>
            <LogOut size={17} aria-hidden="true" />
            <span className="sr-only">{t("יציאה", "Sign out")}</span>
          </button>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span className="breadcrumb">
            {formatDay(today, settings.language, {weekday: "long", day: "numeric", month: "long"})}
          </span>
          <div className="topbar-actions">
            <Link className="mobile-settings-button" href="/?view=settings" aria-label={t("הגדרות", "Settings")} aria-current={view === "settings" ? "page" : undefined}><Settings2 size={20} aria-hidden="true" /></Link>
            <button className="mobile-assistant-button" type="button" aria-label={t("פתיחת העוזר", "Open assistant")} onClick={()=>document.getElementById("lifeos-assistant-launcher")?.click()}><MessageCircle size={21} aria-hidden="true"/></button>
            <NotificationCenter csrf={csrf} initiallyOpen={search.get("notifications") === "open"} data={notifications} settings={settings} t={t}
              onAction={actOnUpdate}
              onRead={readUpdates}
              onSave={async value => { setNotifications(await api<NotificationFeed>("notifications/preferences", "PUT", value, csrf)); }}
              onRefresh={refreshUpdates}
              onUnauthorized={requireReauthentication}
              onOpen={openUpdate} onDiscuss={accountMode ? discussUpdate : undefined} />
          <div className="topbar-status">
            <span className="status-dot" />
            {t("מצב מקומי", "Local mode")}
            <span className="topbar-divider" />
            <span>
              {formatDay(today, settings.language, {
                day: "numeric",
                month: "long",
              })}
            </span>
          </div>
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1} aria-labelledby="page-title">
          <div className="page-heading">
            <div>
              {view === "dashboard" && (
                <p className="greeting">
                  <Sun size={16} aria-hidden="true" />
                  {t("טוב שחזרת", "Welcome back")}
                  {settings.display_name ? `, ${settings.display_name}` : ""}
                </p>
              )}
              <h1 id="page-title">
                {view === "dashboard"
                  ? t(
                      `טוב שחזרת${settings.display_name ? `, ${settings.display_name}` : ""}.`,
                      `Welcome back${settings.display_name ? `, ${settings.display_name}` : ""}.`,
                    )
                  : titles[view]}
              </h1>
              <p className="muted">
                {view === "dashboard"
                  ? formatDay(today, settings.language, {
                      weekday: "long",
                      day: "numeric",
                      month: "long",
                      year: "numeric",
                    })
                  : null}
              </p>
            </div>
            {view !== "settings" && view !== "academic" && view !== "timetable" && (
              <Button
                onClick={() =>
                  setEditor(
                    view === "calendar"
                      ? { kind: "event", day: today }
                      : { kind: "task" },
                  )
                }
              >
                <Plus size={18} aria-hidden="true" />
                {view === "calendar"
                  ? t("אירוע חדש", "New event")
                  : t("משימה חדשה", "New task")}
              </Button>
            )}
          </div>
          {stale && (
            <div className="notice" role="status">
              <span>
                {t(
                  "התצוגה אינה מעודכנת. יש לרענן לפני פעולה נוספת.",
                  "The view is outdated. Refresh before another action.",
                )}
              </span>
              <Button
                variant="secondary"
                onClick={async () => {
                  try {
                    await refresh();
                  } catch {
                    setNotice(
                      t(
                        "הרענון נכשל. בדקו שהשרת המקומי פועל.",
                        "Refresh failed. Check the local server.",
                      ),
                    );
                  }
                }}
              >
                {t("רענון", "Refresh")}
              </Button>
            </div>
          )}
          {view === "dashboard" && !stale && [google, moodle, braude].some(sourceOutdated) && (
            <div className="notice dashboard-source-notice" role="status">
              <span>{t("המידע מהחיבורים לא עודכן. מוצג העדכון האחרון שנשמר.", "Connection data is outdated. Showing the last saved update.")}</span>
              <Button variant="ghost" size="small" onClick={() => navigate("settings")}>{t("בדיקת חיבורים", "Check connections")}</Button>
            </div>
          )}
          {(["calendar", "timetable", "academic"] as View[]).includes(view) && sourceOutdated(braude) && (
            <div className="notice" role="status">{t("סנכרון תחנת המידע אינו מעודכן. מערכת השעות מבוססת כרגע על הנתונים האחרונים שנשמרו.", "The student portal sync is outdated. The timetable currently uses the last saved data.")}</div>
          )}
          {notice && (
            <div className="notice" role="status">
              <span>{notice}</span>
              <Button
                variant="ghost"
                size="icon"
                aria-label={t("סגירה", "Close")}
                onClick={() => setNotice("")}
              >
                <X size={16} aria-hidden="true" />
              </Button>
            </div>
          )}
          {view === "dashboard" && (
            <>
              <div className="home-dashboard-grid">
                <div className="home-work">
                  <UpcomingEvent courses={courses} tasks={tasks} events={events} now={now} settings={settings} t={t} />
              <HomeFocusTasks onShowAll={() => navigate("tasks")} tasks={tasks} {...taskProps} stale={stale || !!(moodle?.configured && (!moodle.connected || moodle.stale || moodle.error))} />
              <div className="dashboard-columns">
                <details className="panel agenda-panel compact-agenda"><summary>{t("סדר היום", "Today’s schedule")}<span className="subtle-badge">{todayEvents.length}</span><ChevronLeft size={18} aria-hidden="true"/></summary>
                  <div className="panel-heading">
                    <div className="heading-with-icon">
                      <CalendarDays size={20} aria-hidden="true" />
                      <h2>{t("על סדר היום", "On your schedule")}</h2>
                    </div>
                    <Button
                      variant="ghost"
                      size="small"
                      onClick={() => navigate("calendar")}
                    >
                      {t("ליומן המלא", "Full calendar")}
                      <ArrowUpLeft
                        className="rtl-chevron"
                        size={15}
                        aria-hidden="true"
                      />
                    </Button>
                  </div>
                  <div className="agenda-date">
                    {formatDay(today, settings.language, {
                      weekday: "long",
                      day: "numeric",
                      month: "long",
                    })}
                    <span className="subtle-badge">{t("היום", "Today")}</span>
                  </div>
                  <Agenda events={todayEvents} {...agendaProps} />
                  <div className="panel-footer">
                    <button
                      className="text-button"
                      onClick={() => setEditor({ kind: "event", day: today })}
                    >
                      <Plus size={16} aria-hidden="true" />
                      {t(
                        "לפנות זמן למשהו חשוב",
                        "Make time for something important",
                      )}
                    </button>
                  </div>
                </details>

              </div>
                </div>
                <aside className="home-updates" aria-label={t("עדכונים ותכנון", "Updates and planning")}>
              <DayOverviewRail events={events} tasks={tasks} now={now} settings={settings} t={t}/>
              <PersonalUpdates data={notifications} settings={settings} now={now} t={t} disabled={busy || stale} onOpen={openUpdate}
                onShowAll={() => document.getElementById("lifeos-notification-center")?.click()}
                onRead={readUpdates} onAction={actOnUpdate} onRefresh={refreshUpdates} onUnauthorized={requireReauthentication} onDiscuss={accountMode ? discussUpdate : undefined} />
              {accountMode && <details className="calm-followups"><summary>{t("הבקשות שלי", "My requests")}</summary><AssistantRequests hideWhenEmpty csrf={csrf} revision={requestRevision} settings={settings} t={t} onOpen={openTrackedRequest} onChanged={refreshUpdates} onUnauthorized={requireReauthentication} /></details>}
              {accountMode && <details className="home-planning-fold"><summary>{t("הצעות לזמן עבודה", "Work time suggestions")}</summary>
              <PlanningNudge revision={planningRevision} csrf={csrf} settings={settings} t={t} disabled={busy || stale} onChanged={refresh} onUnauthorized={requireReauthentication} />
              </details>}
              {moodle?.configured&&<details className="calm-source-updates"><summary>{t("שינויים במטלות", "Assignment changes")}</summary><MoodleUpdates status={moodle} settings={settings} csrf={csrf} t={t} onUnauthorized={requireReauthentication} onDay={start=>router.push(`/?view=calendar&day=${start.length===10?start:dayKey(new Date(start),settings.timezone)}`)}/></details>}
                </aside>
                <div className="home-mail">
              <DailyMail csrf={csrf} t={t} onUnauthorized={requireReauthentication} onConnect={() => navigate("settings")} onCreateTask={draft=>setEditor({kind:"task",draft})} onCreateEvent={draft=>setEditor({kind:"event",draft})} />
                </div>
              </div>
              <details className="dashboard-more" open={search.get("briefing") === "week" || search.get("briefing") === "day"}><summary>{t("תכנון, סיכומים וחיבורים", "Planning, reviews and connections")}<ChevronLeft size={18} aria-hidden="true"/></summary><section className="dashboard-toolbox" aria-label={t("תכנון ותמונה רחבה", "Planning and insights")}><details className="dashboard-tool" open={search.get("briefing") === "week" || search.get("briefing") === "day"}><summary>{t("מבט יומי ושבועי", "Day and week overview")}<ChevronLeft size={18} aria-hidden="true"/></summary><div className="dashboard-tool-body"><PlanningBriefing key={search.get("briefing") === "week" ? "week" : "day"} initialWeek={search.get("briefing") === "week"} tasks={tasks} events={events} now={now} settings={settings} t={t}
                stale={stale || [google, moodle, braude].some(sourceOutdated)}
                onDay={day => router.push(`/?view=calendar&day=${day}`)} onTask={taskProps.onEdit} onTasks={() => navigate("tasks")} /></div></details><details className="dashboard-tool"><summary>{t("דברים שכדאי לשים לב אליהם", "Things to watch")}<ChevronLeft size={18} aria-hidden="true"/></summary><div className="dashboard-tool-body"><RecommendationsPanel data={recommendations} settings={settings} t={t} onNavigate={navigate} onRefresh={refresh} onUnauthorized={requireReauthentication} onDismiss={async id => { setRecommendations(await api<RecommendationFeed>("recommendations/dismiss", "POST", { id }, csrf)); }} /></div></details><details className="dashboard-tool"><summary>{t("למצוא זמן למשימות", "Make time for tasks")}<ChevronLeft size={18} aria-hidden="true"/></summary><div className="dashboard-tool-body"><TaskPlanner tasks={openTasks} settings={settings} today={today} csrf={csrf} t={t} onChanged={refresh} onUnauthorized={requireReauthentication} onDay={day => router.push(`/?view=calendar&day=${day}`)} /></div></details><details className="dashboard-tool"><summary>{t("איך עבר השבוע", "Weekly review")}<ChevronLeft size={18} aria-hidden="true"/></summary><div className="dashboard-tool-body"><WeeklyReview settings={settings} revision={tasks} t={t} onUnauthorized={requireReauthentication} onTask={id => { const task = tasks.find(task => task.id === id); if (task) taskProps.onEdit(task); else navigate("tasks"); }} /></div></details><details className="dashboard-tool"><summary>{t("תמונת הלימודים שלי", "Study overview")}<ChevronLeft size={18} aria-hidden="true"/></summary><div className="dashboard-tool-body"><AcademicSnapshot settings={settings} csrf={csrf} revision={tasks} t={t} onUnauthorized={requireReauthentication} onCourse={id=>router.push(`/?view=academic&course=${encodeURIComponent(id)}`)}/></div></details></section>
              <details className="dashboard-connections"><summary>{t("מצב החיבורים", "Connection status")}</summary>
              <section className="connections-strip">
                <div className="connection-intro">
                  <Unplug size={21} aria-hidden="true" />
                  <div>
                    <h2>
                      {t(
                        "כל החיבורים, במקום אחד",
                        "Your connections, together",
                      )}
                    </h2>
                    <p>
                      {t(
                        "נהלו חיבורים וסנכרון בהגדרות.",
                        "Manage connections and synchronization in Settings.",
                      )}
                    </p>
                  </div>
                </div>
                <div className="provider-list">
                  <ProviderHealth name="Google Calendar" source={google} t={t} />
                  <ProviderHealth name="Gmail" source={gmail} t={t} />
                  <ProviderHealth name="Moodle" source={moodle} t={t} />
                  <ProviderHealth name={t("תחנת המידע", "Student portal")} source={braude} t={t} />
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t("הגדרות חיבורים", "Connection settings")}
                  onClick={() => navigate("settings")}
                >
                  <ChevronLeft
                    className="rtl-chevron"
                    size={18}
                    aria-hidden="true"
                  />
                </Button>
              </section>
              </details>
              </details>
            </>
          )}
          {view === "tasks" && (
            <section className="panel">
              <div className="panel-heading">
                <h2>{t("כל צעד נחשב", "Every step counts")}</h2>
                <div className="segmented">
                  {(["open", "all", "completed"] as const).map((f) => (
                    <button
                      key={f}
                      aria-pressed={filter === f}
                      onClick={() => setFilter(f)}
                    >
                      {f === "open"
                        ? t("פתוחות", "Open")
                        : f === "all"
                          ? t("הכול", "All")
                          : t("הושלמו", "Completed")}
                    </button>
                  ))}
                </div>
              </div>
              <TaskList
                compact
                tasks={sorted.filter(
                  (task) =>
                    filter === "all" ||
                    (filter === "completed" ? task.completed : !task.completed),
                )}
                {...taskProps}
              />
            </section>
          )}
          {view === "calendar" && (
            <>
            <RecurringEvents csrf={csrf} settings={settings} today={today} t={t} onChanged={refresh} onUnauthorized={requireReauthentication} />
            <CalendarView
              key={calendarDayParameter(search.get("day")) ?? "default-calendar"}
              initialDay={calendarDayParameter(search.get("day"))}
              events={events.filter(event=>!isClassEvent(event))}
              tasks={tasks}
              settings={settings}
              today={today}
              t={t}
              onEdit={agendaProps.onEdit}
              onDelete={agendaProps.onDelete}
              onAdd={(day) => setEditor({ kind: "event", day })}
              busy={busy}
            />
            </>
          )}
          {view === "timetable" && <ClassTimetable courses={courses} key={calendarDayParameter(search.get("day")) ?? "current-timetable"} initialDay={calendarDayParameter(search.get("day"))} events={events} today={today} settings={settings} t={t}/> }
          {view === "academic" && (
            <AcademicView
              sourceEvents={events.filter(event=>event.source==="braude")}
              settings={settings}
              tasks={tasks}
              today={today}
              now={now}
              onDay={day => router.push(`/?view=calendar&day=${day}`)}
              csrf={csrf}
              t={t}
              courseId={search.get("course")}
              onSelect={(id) =>
                router.push(
                  id ? `/?view=academic&course=${id}` : "/?view=academic",
                )
              }
              onChanged={refresh}
              onUnauthorized={requireReauthentication}
            />
          )}
          {view === "settings" && (
            <SettingsView
              accountMode={accountMode}
              settings={settings}
              t={t}
              csrf={csrf}
              onChanged={refresh}
              onUnauthorized={requireReauthentication}
              onSave={async (value) => {
                await mutate("settings", "PUT", value);
              }}
            />
          )}
          <footer className="workspace-footer">
            <span translate="no">LifeOS</span>
            <span>
              <bdi>{settings.timezone}</bdi>
            </span>
          </footer>
        </main>
      </div>
      {editor && (
        <RecordForm
          editor={editor}
          settings={settings}
          t={t}
          onClose={() => setEditor(null)}
          onSave={async (kind, body, id) => {
            await mutate(
              `${kind === "task" ? "tasks" : "events"}${id ? `/${id}` : ""}`,
              id ? "PUT" : "POST",
              body,
            );
            setNotice(t("נשמר במרחב שלך.", "Saved in your workspace."));
          }}
        />
      )}
      {reauthenticate && (
        <Reauthenticate
          t={t}
          onCancel={() => setReauthenticate(false)}
          onLogin={async (password) => {
            const session = await api<{ csrf: string }>("session", "POST", {
              password,
              ...(accountMode ? { login: accountLogin } : {}),
            });
            accountIdentity.current = { ...accountIdentity.current, csrf: session.csrf };
            setCsrf(session.csrf);
            setReauthenticate(false);
          }}
        />
      )}
      <AssistantChat ref={assistantRef} csrf={csrf} settings={settings} t={t} onChanged={refresh} onRequestsChanged={() => setRequestRevision(value => value + 1)} onUnauthorized={requireReauthentication} />
      {pendingDelete && (
        <Modal
          open
          onClose={() => {
            if (!busy) setPendingDelete(null);
          }}
          title={t("למחוק את הפריט?", "Delete this item?")}
          description={pendingDelete.record.title}
          closeLabel={t("סגירה", "Close")}
        >
          <p className="muted">
            {t(
              "הפעולה תסיר את הפריט מהמידע המקומי ולא ניתן לבטל אותה.",
              "This permanently removes the item from your local data.",
            )}
          </p>
          <div className="form-actions">
            <Button variant="danger" disabled={busy} onClick={remove}>
              {busy ? t("מוחק…", "Deleting…") : t("מחיקה", "Delete")}
            </Button>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => setPendingDelete(null)}
            >
              {t("ביטול", "Cancel")}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
