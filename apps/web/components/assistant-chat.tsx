"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useImperativeHandle,
  type Ref,
  useState,
  type FormEvent,
} from "react";
import { Check, LoaderCircle, MessageCircle, Send } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { AssistantChatHandle, TrackedRequest } from "@/lib/assistant-requests";
import { weekdayNames } from "@/lib/planning-preferences";
import type { Settings, Translate } from "@/lib/types";
import { BuiltInHelp } from "./built-in-help";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";

type Proposal = {
  change_from?: {start:string;end:string};
  id: string;
  kind: "task" | "event";
  payload: { title: string; due?: string; start?: string; end?: string };
  preference_source?: { daily_limit_minutes?:number; weekdays?:number[]; window_start: string; window_end: string; default_duration: number | null };
};
type HistoryState = { enabled: boolean; generation: number };
type History = HistoryState & {
  stored_count: number;
  available_turns: number;
  truncated: boolean;
  messages: {
    id: string;
    role: "user" | "assistant";
    text: string;
    created_at: string;
  }[];
};
type Answer = {
  request_tracking_updated?: boolean;
  history_state?: HistoryState;
  history_saved?: boolean;
  history_error?: boolean;
  history_discarded?: boolean;
  history_replayed?: boolean;
  reply: string;
  proposal: Proposal | null;
  schedule?: {
    truncated?: boolean;
    events: { title: string; start: string }[];
    tasks: { title: string; due: string }[];
  };
};
type Entry = {
  id: string;
  historical?: boolean;
  excludeFromContext?: boolean;
  role: "user" | "assistant";
  text: string;
  result?: Answer;
  saved?: boolean;
  cancelled?: boolean;
};
type Status = { ready: boolean; model: string; local: boolean; state: string };

export function AssistantChat({
  csrf,
  settings,
  t,
  onChanged,
  onUnauthorized,
  ref,
  onRequestsChanged,
}: {
  csrf: string;
  settings: Settings;
  t: Translate;
  onChanged: () => Promise<void>;
  onUnauthorized: () => void;
  ref?: Ref<AssistantChatHandle>;
  onRequestsChanged?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [historyData, setHistoryData] = useState<History | null>(null);
  const historyRef = useRef<History | null>(null);
  const [historyError, setHistoryError] = useState(false);
  const [clearPrompt, setClearPrompt] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [requestContext, setRequestContext] = useState<TrackedRequest | null>(null);
  useImperativeHandle(ref, () => ({ openRequest(item) {
    if (busy) return false;
    const proposal = item.resume_proposal;
    if (proposal) setEntries(previous => previous.some(entry => entry.result?.proposal?.id === proposal.id) ? previous : [...previous, {
      id: `resumed:${proposal.id}`, role: "assistant", text: t("הצעה שמורה שממתינה לאישור שלך.", "A saved proposal awaiting your confirmation."),
      excludeFromContext: true, result: { reply: "", proposal },
    }]);
    setRequestContext(item); setOpen(true); setError(""); return true;
  } }), [busy, t]);
  const transcript = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (transcript.current)
      transcript.current.scrollTop = transcript.current.scrollHeight;
  }, [entries, busy]);
  const applyHistory = useCallback((next: History) => {
    const changed =
      historyRef.current !== null &&
      historyRef.current.generation !== next.generation;
    historyRef.current = next;
    setHistoryData(next);
    setHistoryError(false);
    setEntries((previous) => {
      const existing = changed ? [] : previous;
      if (!next.enabled) return changed ? [] : existing;
      const byId = new Map(existing.map((entry) => [entry.id, entry]));
      const loaded = next.messages.map(
        (message) =>
          byId.get(message.id) ?? {
            id: message.id,
            role: message.role,
            text: message.text,
            historical: true,
          },
      );
      const ids = new Set(loaded.map((entry) => entry.id));
      return [
        ...loaded,
        ...existing.filter((entry) => !ids.has(entry.id)),
      ].slice(-100);
    });
  }, []);
  const loadHistory = useCallback(async () => {
    try {
      applyHistory(await api<History>("assistant/history"));
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      setHistoryError(true);
    }
  }, [applyHistory, onUnauthorized]);
  useEffect(() => {
    if (!open) return;
    let active = true;
    void (async () => {
      try {
        const next = await api<History>("assistant/history");
        if (active) applyHistory(next);
      } catch (error) {
        if (active) {
          if (error instanceof ApiError && error.status === 401)
            onUnauthorized();
          setHistoryError(true);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [open, csrf, applyHistory, onUnauthorized]);
  async function historyAction(clear: boolean) {
    setBusy(true);
    setHistoryError(false);
    try {
      const next = clear
        ? await api<History>("assistant/history", "DELETE", undefined, csrf)
        : await api<History>(
            "assistant/history",
            "PUT",
            { enabled: !historyData?.enabled },
            csrf,
          );
      setEntries([]);
      setText("");
      setClearPrompt(false);
      applyHistory(next);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      setHistoryError(true);
    } finally {
      setBusy(false);
    }
  }
  async function loadStatus() {
    try {
      setStatus(await api<Status>("assistant/status"));
      setError("");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      setError("unavailable");
    }
  }
  useEffect(() => {
    if (!open) return;
    let active = true;
    void (async () => {
      try {
        const result = await api<Status>("assistant/status");
        if (active) setStatus(result);
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) onUnauthorized();
        if (active) setError("unavailable");
      }
    })();
    return () => {
      active = false;
    };
  }, [open, csrf, onUnauthorized]);
  function format(value: string) {
    if (value.length === 10) return value.split("-").reverse().join("/");
    return new Intl.DateTimeFormat(settings.language, {
      dateStyle: "short",
      timeStyle: "short",
      timeZone: settings.timezone,
    }).format(new Date(value));
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!text.trim() || busy || !status?.ready || requestContext?.status === "done") return;
    const message = text.trim();
    const history = entries
      .filter((entry) => !entry.excludeFromContext)
      .slice(-6)
      .map((entry) => ({
        role: entry.role,
        content: (
          entry.text +
          (entry.result?.proposal && !entry.result.proposal.preference_source
            ? " " + JSON.stringify(entry.result.proposal.payload)
            : "")
        ).slice(0, 600),
      }));
    const turnId = crypto.randomUUID();
    setEntries((previous) => [
      ...previous.slice(-99),
      { id: `${turnId}:user`, role: "user", text: message },
    ]);
    setBusy(true);
    setError("");
    try {
      const result = await api<Answer>(
        "assistant/chat",
        "POST",
        {
          message,
          history,
          turn_id: turnId,
          history_generation: historyRef.current?.generation,
          ephemeral: historyError || !historyRef.current,
          request_id: requestContext?.id,
          request_version: requestContext?.version,
        },
        csrf,
      );
      if (result.history_state && historyRef.current) {
        const next = {
          ...historyRef.current,
          ...result.history_state,
          stored_count: Math.min(
            200,
            historyRef.current.stored_count +
              (result.history_saved && !result.history_replayed ? 1 : 0),
          ),
        };
        historyRef.current = next;
        setHistoryData(next);
      }
      if (result.history_discarded) {
        setEntries([
          { id: `${turnId}:user`, role: "user", text: message, excludeFromContext: true },
          { id: `${turnId}:assistant`, role: "assistant", text: result.reply, result, excludeFromContext: true },
        ]);
        setError("history_changed");
      } else
        setEntries((previous) => [
          ...previous.slice(-99),
          {
            id: `${turnId}:assistant`,
            role: "assistant",
            text: result.reply,
            result,
          },
        ]);
      if (result.history_error) setHistoryError(true);
      if (requestContext) {
        onRequestsChanged?.();
        try { setRequestContext(await api<TrackedRequest>(`assistant/requests/${requestContext.id}`)); }
        catch { setError("request_refresh"); }
        if (result.request_tracking_updated === false) setError("request_refresh");
      }
      setText("");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      setError(
        error instanceof ApiError && error.message === "assistant_resource_limit"
          ? "resource"
          : error instanceof ApiError && error.status === 429
          ? "busy"
          : error instanceof ApiError && error.status === 409
          ? "changed"
          : error instanceof ApiError && error.status === 404 && requestContext
          ? "request_missing"
          : error instanceof ApiError && error.status === 502
          ? "invalid"
          : "unavailable",
      );
    } finally {
      setBusy(false);
    }
  }
  async function confirm(entry: Entry) {
    if (busy || !entry.result?.proposal || entry.saved) return;
    setBusy(true);
    setError("");
    try {
      const saved = await api<{request_tracking_warning?: boolean}>(
        "assistant/confirm",
        "POST",
        { id: entry.result.proposal.id },
        csrf,
      );
      setEntries((previous) =>
        previous.map((item) =>
          item.id === entry.id ? { ...item, saved: true } : item,
        ),
      );
      onRequestsChanged?.();
      if (requestContext) {
        try { setRequestContext(await api<TrackedRequest>(`assistant/requests/${requestContext.id}`)); }
        catch { setError("request_refresh"); }
      }
      if (saved.request_tracking_warning) setError("request_refresh");
      try {
        await onChanged();
      } catch {
        setError("refresh");
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      setError(
        error instanceof ApiError && error.message === "assistant_resource_limit"
          ? "resource"
          : error instanceof ApiError && error.status === 404
          ? "expired"
          : error instanceof ApiError && error.status === 409
            ? "conflict"
            : "unavailable",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Button id="lifeos-assistant-launcher" className="assistant-launcher" onClick={() => setOpen(true)}>
        <MessageCircle size={20} aria-hidden="true" />
        {t("העוזר האישי", "Personal assistant")}
      </Button>
      {open && (
        <Modal
          open
          onClose={() => setOpen(false)}
          title={t("העוזר האישי", "Personal assistant")}
          description={t(
            "ניהול זמן ותפעול LifeOS · מודל מקומי בלבד",
            "Time management and LifeOS help · Local model only",
          )}
          closeLabel={t("סגירה", "Close")}
        >
          <div className="assistant-chat">
            {requestContext && <div className="assistant-request-context">
              <strong dir="auto">{requestContext.title}{requestContext.course_name && ` · ${requestContext.course_name}`}</strong>
              <p className="field-help">{t("הקשר מהעדכון שנשמר ב־", "Reference saved on ")}{format(requestContext.created_at)}{requestContext.due ? ` · ${t("מועד שמור", "Saved date")}: ${format(requestContext.due)}` : ""}. {t("פתיחת הבקשה אינה שולחת הודעה. המידע אינו בדיקת מקור חיה.", "Opening sends no message. This is not a live source check.")}</p>
              {requestContext.status === "done" && <p role="status">{t("הבקשה טופלה. אפשר לפתוח אותה מחדש ברשימת הבקשות.", "This request was handled. Reopen it from My requests.")}</p>}
              <Button size="small" variant="ghost" disabled={busy} onClick={() => { setRequestContext(null); setError(""); }}>{t("חזרה לשיחה רגילה", "Return to general chat")}</Button>
              <Button size="small" variant="ghost" disabled={busy} onClick={() => void api<TrackedRequest>(`assistant/requests/${requestContext.id}`).then(item => { setRequestContext(item); setError(""); }).catch(() => setError("request_refresh"))}>{t("רענון הבקשה", "Refresh request")}</Button>
            </div>}
            <p className="assistant-scope">
              {t(
                "אפשר להוסיף משימות, לתכנן אירועים, למצוא זמן פנוי ולשאול איך משתמשים באפליקציה. בלי פתרון שיעורי בית. כל שמירה דורשת אישור שלך.",
                "Add tasks, plan events, find free time and ask how to use the app. No homework solutions. Every save needs your confirmation.",
              )}
            </p>
            <BuiltInHelp t={t} onUnauthorized={onUnauthorized} />
            <details className="assistant-history">
              <summary>
                {t("היסטוריית שיחה מקומית", "Local conversation history")} ·{" "}
                {historyData
                  ? historyData.enabled
                    ? t("פעילה", "On")
                    : t("כבויה", "Off")
                  : t("לא זמינה כרגע", "Unavailable")}
              </summary>
              <p className="field-help">
                {t(
                  "כבויה כברירת מחדל. בהפעלה נשמר טקסט במחשב עד 30 יום ועד 200 תורות, והוא נכלל בגיבוי. נטענות עד 50 תורות אחרונות; הצעות ישנות נטענות כטקסט בלבד.",
                  "Off by default. Opt in to store text locally for up to 30 days and 200 turns, included in backups. Up to 50 recent turns load as text only; old proposals cannot be approved from history.",
                )}
              </p>
              <p className="field-help">
                {t(
                  "כיבוי מפסיק לשמור הודעות חדשות ומתחיל שיחה חדשה בתצוגה. כדי למחוק שיחות שכבר נשמרו, בחרו ״מחיקת ההיסטוריה״. טקסט השיחה אינו מידע אישי מאומת.",
                  "Turning off stops saving new messages and starts a fresh view. To delete previously saved conversations, choose Clear saved history. Conversation text is not verified personal memory.",
                )}
              </p>
              <div className="google-actions">
                <Button
                  size="small"
                  variant="secondary"
                  disabled={busy || !historyData}
                  onClick={() => void historyAction(false)}
                >
                  {historyData?.enabled
                    ? t("כיבוי שמירת שיחה", "Turn off history")
                    : t("הפעלת שמירת שיחה", "Enable history")}
                </Button>
                <Button
                  size="small"
                  variant="ghost"
                  disabled={busy || !historyData}
                  onClick={() => setClearPrompt(true)}
                >
                  {t("מחיקת ההיסטוריה", "Clear saved history")}
                </Button>
                <Button
                  size="small"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => void loadHistory()}
                >
                  {t("רענון היסטוריה", "Refresh history")}
                </Button>
              </div>
              {clearPrompt && (
                <div className="history-clear-confirm">
                  <p>
                    {t(
                      "למחוק את השיחה השמורה? משימות ואירועים לא ישתנו. עותקים שכבר הורדת בגיבויים עשויים עדיין להכיל אותה.",
                      "Delete saved conversation text? Tasks/events stay unchanged. Previously downloaded backups may still contain it.",
                    )}
                  </p>
                  <div className="google-actions">
                    <Button
                      size="small"
                      variant="danger"
                      disabled={busy}
                      onClick={() => void historyAction(true)}
                    >
                      {t("אישור מחיקת ההיסטוריה", "Confirm history deletion")}
                    </Button>
                    <Button
                      size="small"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => setClearPrompt(false)}
                    >
                      {t("ביטול", "Cancel")}
                    </Button>
                  </div>
                </div>
              )}
              {historyError && (
                <p role="status" className="field-help">
                  {t(
                    "שמירת ההיסטוריה אינה זמינה כרגע; התשובה וההצעה הנוכחיות עדיין ניתנות לבדיקה. אפשר להמשיך בלי שמירה.",
                    "History storage is unavailable; the current answer/proposal remains reviewable. You can continue without saving history.",
                  )}
                </p>
              )}
              {historyData?.truncated && (
                <p className="field-help">
                  {t(
                    "מוצגות עד 50 תורות שמורות אחרונות.",
                    "Showing up to 50 recent saved turns.",
                  )}
                </p>
              )}
            </details>
            {!status ? (
              <p role="status">
                {t("בודק חיבור למודל…", "Checking local model…")}
              </p>
            ) : (
              !status.ready && (
                <div className="notice" role="status">
                  <span>
                    {status.state === "disabled_on_server" ? t(
                      "צ׳אט AI אינו מופעל בשרת הזה. העזרה המובנית ותכנון המשימות זמינים באפליקציה.",
                      "AI chat is not enabled on this server. Built-in help and task planning are available in the app.",
                    ) : t(
                      "המודל המקומי אינו זמין כרגע. יש להפעיל Ollama ולהתקין את מודל העוזר.",
                      "Local model unavailable. Start Ollama and install the assistant model.",
                    )}
                  </span>
                  <Button
                    variant="ghost"
                    size="small"
                    onClick={() => void loadStatus()}
                  >
                    {t("בדוק שוב", "Check again")}
                  </Button>
                </div>
              )
            )}
            <div
              ref={transcript}
              className="assistant-transcript"
              role="log"
              aria-label={t("השיחה עם העוזר", "Assistant conversation")}
            >
              {entries.length === 0 && (
                <p className="muted">
                  {t(
                    "לדוגמה: ״תוסיף משימה להתקשר לרופא מחר״ או ״מצא שעה פנויה מחר לפגישה״.",
                    "Try: “Add a task to call the doctor tomorrow” or “Find an hour tomorrow for a meeting.”",
                  )}
                </p>
              )}
              {entries.map((entry) => (
                <article
                  className={`assistant-message assistant-${entry.role}`}
                  key={entry.id}
                >
                  <small>
                    {entry.role === "user"
                      ? t("אתה", "You")
                      : t("העוזר", "Assistant")}
                    {entry.historical &&
                      ` · ${t("טקסט משיחה שמורה", "Saved conversation text")}`}
                  </small>
                  <p dir="auto">{entry.text}</p>
                  {entry.result?.schedule?.truncated && (
                    <p className="field-help">
                      {t(
                        "מוצגים עד 30 אירועים ו־30 משימות ראשונים. הרשימה המלאה ביומן ובמשימות.",
                        "Showing the first 30 events and 30 tasks. See the calendar/tasks for the full list.",
                      )}
                    </p>
                  )}
                  {entry.result?.schedule && (
                    <ul>
                      {entry.result.schedule.events.map((event, index) => (
                        <li key={`e${index}`}>
                          {event.title} · {format(event.start)}
                        </li>
                      ))}
                      {entry.result.schedule.tasks.map((task, index) => (
                        <li key={`t${index}`}>
                          {task.title} · {format(task.due)}
                        </li>
                      ))}
                      {entry.result.schedule.events.length +
                        entry.result.schedule.tasks.length ===
                        0 && (
                        <li>
                          {t(
                            "אין פריטים בטווח הזה.",
                            "No items in that range.",
                          )}
                        </li>
                      )}
                    </ul>
                  )}
                  {entry.result?.proposal && !entry.cancelled && (
                    <div className="assistant-proposal">
                      <strong>{entry.result.proposal.payload.title}</strong>
                      <p>
                        {entry.result.proposal.change_from ? t("הזזת משבצת עבודה מקומית", "Move a linked local work block") : entry.result.proposal.kind === "task"
                          ? t("משימה חדשה", "New task")
                          : t("אירוע אישי חדש", "New personal event")}
                      </p>
                      {entry.result.proposal.change_from && <p>{t("הזמן הקודם", "Previous time")}: {format(entry.result.proposal.change_from.start)} — {format(entry.result.proposal.change_from.end)}</p>}
                      {entry.result.proposal.payload.due && (
                        <p>{format(entry.result.proposal.payload.due)}</p>
                      )}
                      {entry.result.proposal.payload.start && (
                        <p>
                          {format(entry.result.proposal.payload.start)}
                          {entry.result.proposal.payload.end && (
                            <> — {format(entry.result.proposal.payload.end)}</>
                          )}
                        </p>
                      )}
                      <small>{settings.timezone}</small>
                      {entry.result.proposal.preference_source && <p className="field-help">{t("מבוסס על העדפות ששמרת", "Based on your saved preferences")} · <bdi>{entry.result.proposal.preference_source.window_start}–{entry.result.proposal.preference_source.window_end}</bdi>{entry.result.proposal.preference_source.weekdays && <> · {t("ימי תכנון", "Planning weekdays")}: {weekdayNames(entry.result.proposal.preference_source.weekdays,settings.language)}</>}{entry.result.proposal.preference_source.daily_limit_minutes!=null&&<> · {t("תקרה יומית","Daily cap")}: {entry.result.proposal.preference_source.daily_limit_minutes} {t("דקות מתוזמנות","scheduled minutes")}</>}{entry.result.proposal.preference_source.default_duration !== null && <> · {t("משך ברירת מחדל", "Default duration")}: {entry.result.proposal.preference_source.default_duration} {t("דקות", "minutes")}</>}</p>}
                      {entry.saved ? (
                        <p className="assistant-saved" role="status">
                          <Check size={16} />
                          {t("נשמר בהצלחה", "Saved successfully")}
                        </p>
                      ) : (
                        <div className="form-actions">
                          <Button
                            disabled={busy}
                            onClick={() => void confirm(entry)}
                          >
                            {t("אישור ושמירה", "Confirm and save")}
                          </Button>
                          <Button
                            variant="ghost"
                            disabled={busy}
                            onClick={() =>
                              setEntries((previous) =>
                                previous.map((item) =>
                                  item.id === entry.id
                                    ? { ...item, cancelled: true }
                                    : item,
                                ),
                              )
                            }
                          >
                            {t("ביטול ההצעה", "Dismiss proposal")}
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                </article>
              ))}
              {busy && (
                <p className="assistant-waiting" role="status">
                  <LoaderCircle size={16} className="spin" />
                  {t("מעבד במחשב שלך…", "Processing on your computer…")}
                </p>
              )}
            </div>
            {error && (
              <p role="alert" className="error-message">
                {error === "busy" ? t("העוזר מטפל כרגע בבקשה אחרת. נסו שוב בעוד רגע.", "The assistant is handling another request. Wait a moment and try again.")
                  : error === "request_missing" ? t("הבקשה כבר אינה זמינה. אפשר לחזור לשיחה רגילה ולהמשיך.", "This request is no longer available. Return to general chat to continue.")
                  : error === "changed" ? t("הבקשה או המידע השתנו. רעננו לפני ניסיון נוסף.", "The request or its information changed. Refresh it before trying again.")
                  : error === "request_refresh" ? t("התשובה או השמירה התקבלו, אך יש לרענן את מעקב הבקשה לפני המשך.", "The answer or save succeeded, but refresh request tracking before continuing.") : error === "resource"
                  ? t(
                      "בדיקת היומן חרגה ממגבלת המשאבים. לא הושלמה בדיקת זמינות; נסו שוב. הטיוטה וההצעה נשארות כאן.",
                      "Calendar checking exceeded its resource limit. Availability was not fully checked; retry. Your draft and proposal stay here.",
                    )
                  : error === "history_changed"
                  ? t(
                      "העדפות השיחה או ההיסטוריה השתנו. ההקשר אופס; אפשר לשלוח בקשה חדשה.",
                      "History or its preferences changed. Context was reset; send a fresh request.",
                    )
                  : error === "expired"
                    ? t(
                        "ההצעה פגה. בקש הצעה חדשה.",
                        "Proposal expired. Ask for a new one.",
                      )
                    : error === "conflict"
                      ? t(
                          "היומן, אזור הזמן, העדפות התכנון או שעת ההצעה השתנו. בקש הצעה חדשה.",
                          "The calendar, timezone, planning preferences or proposed time changed. Ask for a new proposal.",
                        )
                      : error === "refresh"
                        ? t(
                            "נשמר, אך יש לרענן את התצוגה.",
                            "Saved, but the view needs refreshing.",
                          )
                        : error === "invalid"
                          ? t(
                              "לא הצלחתי להבין בבטחה. נסה לפרט תאריך, שעה ומשך.",
                              "Could not interpret safely. Specify date, time and duration.",
                            )
                          : t(
                              "העוזר המקומי לא ענה. בדוק ש־Ollama פועל ונסה שוב. דבר לא נשמר ללא אישור.",
                              "The local assistant did not respond. Check Ollama and retry. Nothing is saved without confirmation.",
                            )}
              </p>
            )}
            <form onSubmit={send} className="assistant-input">
              <label className="sr-only" htmlFor="assistant-message">
                {t("הודעה לעוזר", "Message the assistant")}
              </label>
              <textarea
                id="assistant-message"
                value={text}
                onChange={(event) => setText(event.target.value)}
                maxLength={1500}
                rows={2}
                disabled={busy}
                placeholder={t(
                  "מה תרצה לתכנן?",
                  "What would you like to plan?",
                )}
              />
              <Button
                type="submit"
                size="icon"
                disabled={busy || !status?.ready || !text.trim() || requestContext?.status === "done"}
                aria-label={t("שליחת הודעה", "Send message")}
              >
                <Send size={18} />
              </Button>
            </form>
          </div>
        </Modal>
      )}
    </>
  );
}
