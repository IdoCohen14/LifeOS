"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Bell, CheckCheck, Moon, Settings2 } from "lucide-react";
import { ApiError } from "@/lib/api";
import { personalUpdate } from "@/lib/personal-update";
import { useBrowserNotifications } from "@/lib/use-browser-notifications";
import type { Settings, Translate } from "@/lib/types";
import type { Recommendation } from "./recommendations-panel";
import { WebPushSettings } from "./web-push-settings";
import { BriefingScheduleSettings } from "./briefing-schedule";
import { BriefingSnapshotCard } from "./briefing-snapshot";
import { Modal } from "./ui/dialog";
import { Button } from "./ui/button";

export type NotificationPreferences = {
  enabled: boolean;
  tasks: boolean;
  conflicts: boolean;
  briefings?: boolean;
  mail?: boolean;
  events?: boolean;
  quiet_enabled: boolean;
  quiet_start: string;
  quiet_end: string;
};
export type BriefingSnapshot = {
  events: number;
  all_day: number;
  minutes: number;
  deadlines: number;
  overdue: number;
  undated: number;
  range_start: string;
  range_end: string;
  generated_at: string;
  timezone: string;
  stale_sources: string[];
};
export type NotificationItem = Omit<Recommendation, "kind" | "target"> & {
  course_name?: string;
  lesson?: boolean;
  instructor?: string;
  class_room?: string;
  request_id?: string;
  academic_kind?: "assignment" | "exam";
  source_updated_at?: number;
  kind: Recommendation["kind"] | "daily_briefing" | "weekly_briefing" | "new_mail" | "upcoming_event" | "moodle_update" | "request_followup";
  target: Recommendation["target"] | "dashboard" | "timetable";
  briefing?: BriefingSnapshot;
  event_source?: string;
  change_kind?: "added" | "changed" | "removed";
  observed_at?: number;
  previous_start?: string|null;
  read: boolean;
  source_ids: string[];
  dismissed?: boolean;
  snoozed_until?: number | null;
};
export type NotificationFeed = {
  items: NotificationItem[];
  hidden?: NotificationItem[];
  hidden_total?: number;
  hidden_truncated?: boolean;
  unread: number;
  truncated: boolean;
  conflicts_limited: boolean;
  quiet: boolean;
  stale_sources: string[];
  preferences: NotificationPreferences;
};

export type NotificationAction = {
  id: string;
  action: "dismiss" | "snooze" | "restore";
  minutes?: 15 | 60 | 1440;
};

export function NotificationCenter({
  data,
  settings,
  t,
  onRead,
  onAction,
  onSave,
  onOpen,
  onDiscuss,
  onRefresh,
  onUnauthorized,
  initiallyOpen = false,
  csrf,
}: {
  data: NotificationFeed | null;
  settings: Settings;
  t: Translate;
  onRead: (ids: string[]) => Promise<void>;
  onAction?: (action: NotificationAction) => Promise<void>;
  onSave: (value: NotificationPreferences) => Promise<void>;
  onOpen: (item: NotificationItem) => void;
  onDiscuss?: (item: NotificationItem) => Promise<void>;
  onRefresh: () => Promise<void>;
  onUnauthorized?: () => void;
  initiallyOpen?: boolean;
  csrf?: string;
}) {
  const tabsRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(initiallyOpen);
  const browser = useBrowserNotifications(
    data,
    settings.language,
    settings.timezone,
  );
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    const receive = (event: MessageEvent) => {
      if (event.data?.type === "lifeos:open-notifications") setOpen(true);
    };
    navigator.serviceWorker.addEventListener("message", receive);
    return () =>
      navigator.serviceWorker.removeEventListener("message", receive);
  }, []);
  const [showHidden, setShowHidden] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onUnauthorized?.();
      setError(
        error instanceof ApiError && error.status === 409
          ? t(
              "ההתראות השתנו. יש לרענן ולנסות שוב.",
              "Notifications changed. Refresh and try again.",
            )
          : t(
              "הפעולה לא הושלמה. אפשר לרענן ולנסות שוב.",
              "Could not complete the action. Refresh and retry.",
            ),
      );
    } finally {
      setBusy(false);
    }
  }
  async function act(value: NotificationAction) {
    await perform(async () => {
      await onAction?.(value);
      tabsRef.current
        ?.querySelector<HTMLButtonElement>('[aria-pressed="true"]')
        ?.focus();
    });
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await perform(() =>
      onSave({
        enabled: form.has("enabled"),
        tasks: form.has("tasks"),
        conflicts: form.has("conflicts"),
        briefings: form.has("briefings"),
        mail: form.has("mail"),
        events: form.has("events"),
        quiet_enabled: form.has("quiet_enabled"),
        quiet_start: String(form.get("quiet_start")),
        quiet_end: String(form.get("quiet_end")),
      }),
    );
  }
  const count = data && !data.quiet ? data.unread : 0;
  const label = data?.quiet
    ? t("מרכז התראות · שעות שקטות", "Notifications · Quiet hours")
    : count
      ? t(`מרכז התראות: ${count} לא נקראו`, `Notifications: ${count} unread`)
      : t("מרכז התראות", "Notifications");
  const items = showHidden ? (data?.hidden ?? []) : (data?.items ?? []);
  const unread = showHidden
    ? []
    : items.filter((item) => !item.read).map((item) => item.id);
  const title = (item: NotificationItem) =>
    item.kind === "daily_briefing"
      ? t("הסיכום היומי שלך מוכן", "Your daily briefing is ready")
      : item.kind === "weekly_briefing"
        ? t("הסיכום השבועי שלך מוכן", "Your weekly briefing is ready")
        : personalUpdate(item, settings, t).subject;
  const format = (value: string) =>
    value.length === 10
      ? value.split("-").reverse().join("/")
      : new Intl.DateTimeFormat(settings.language, {
          dateStyle: "short",
          timeStyle: "short",
          timeZone: settings.timezone,
        }).format(new Date(value));
  return (
    <>
      <Button
        id="lifeos-notification-center"
        className="notification-bell"
        variant="ghost"
        size="icon"
        aria-label={label}
        onClick={() => {
          setError("");
          setOpen(true);
        }}
      >
        {data?.quiet ? (
          <Moon size={18} aria-hidden="true" />
        ) : (
          <Bell size={19} aria-hidden="true" />
        )}
        {count > 0 && (
          <span className="notification-count" aria-hidden="true">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </Button>
      {open && (
        <Modal
          open
          onClose={() => setOpen(false)}
          title={t("מרכז התראות", "Notifications")}
          description={t(
            "מועדים, התנגשויות וסיכומים מהמידע השמור",
            "Deadlines, conflicts and briefings from saved records",
          )}
          closeLabel={t("סגירה", "Close")}
        >
          <div className="notification-toolbar">
            <Button
              variant="secondary"
              size="small"
              disabled={busy}
              onClick={() => void perform(onRefresh)}
            >
              {t("רענון", "Refresh")}
            </Button>
            {unread.length > 0 && (
              <Button
                variant="ghost"
                size="small"
                disabled={busy}
                onClick={() => void perform(() => onRead(unread))}
              >
                <CheckCheck size={16} aria-hidden="true" />
                {t("סימון המוצגות כנקראו", "Mark displayed as read")}
              </Button>
            )}
          </div>
          {data && (
            <div
              className="segmented"
              role="group"
              aria-label={t("תצוגת התראות", "Notification view")}
              ref={tabsRef}
            >
              <button
                aria-pressed={!showHidden}
                onClick={() => setShowHidden(false)}
              >
                {t("פעילות", "Active")}
              </button>
              <button
                aria-pressed={showHidden}
                onClick={() => setShowHidden(true)}
              >
                {t(
                  `מוסתרות (${data.hidden_total ?? 0})`,
                  `Hidden (${data.hidden_total ?? 0})`,
                )}
              </button>
            </div>
          )}
          {error && (
            <p role="alert" className="error-message">
              {error}
            </p>
          )}
          {!data ? (
            <p role="status">
              {t(
                "ההתראות אינן זמינות כרגע. נסו לרענן.",
                "Notifications are unavailable. Try refreshing.",
              )}
            </p>
          ) : (
            <>
              {data.quiet && (
                <p className="field-help">
                  {t(
                    "שעות שקטות פעילות: המונה מוסתר, הרשימה עדיין זמינה.",
                    "Quiet hours are active: the badge is hidden; the list remains available.",
                  )}
                </p>
              )}
              {data.stale_sources.length > 0 && (
                <p role="status" className="field-help">
                  {t(
                    "מידע מיובא עלול להיות לא מעודכן",
                    "Imported information may be outdated",
                  )}
                  : {data.stale_sources.join(", ")}
                </p>
              )}
              {!data.preferences.enabled ? (
                <p>
                  {t(
                    "התראות בתוך האפליקציה כבויות. אפשר להפעיל בהעדפות למטה.",
                    "In-app notifications are off. Enable them in preferences below.",
                  )}
                </p>
              ) : items.length === 0 ? (
                <p className="notification-empty">
                  {t(
                    "אין התראות בקטגוריות שבחרת",
                    "No notifications in your selected categories",
                  )}
                </p>
              ) : (
                <ul className="notification-list">
                  {items.map((item) => (
                    <li
                      key={item.id}
                      className={
                        item.read ? "notification-read" : "notification-unread"
                      }
                    >
                      <span className="notification-kind">
                        {item.briefing
                          ? t("סיכום מתוזמן", "Scheduled briefing")
                          : item.kind === "request_followup" ? t("חזרה לבקשה", "Request follow-up")
                          : item.kind === "moodle_update"
                            ? t("שינוי שזוהה בייצוא Moodle", "Observed Moodle export change")
                          : item.kind === "upcoming_event"
                            ? t("אירוע מתקרב", "Upcoming event")
                          : item.kind === "new_mail"
                            ? t("מייל רלוונטי חדש · Gmail", "New relevant mail · Gmail")
                          : item.kind === "conflict"
                            ? t("התנגשות ביומן", "Calendar conflict")
                            : item.kind === "overdue"
                              ? t("מועד שעבר", "Overdue")
                              : t("מועד קרוב", "Upcoming deadline")}{" "}
                        · {item.read ? t("נקראה", "Read") : t("חדשה", "Unread")}
                      </span>
                      <strong dir="auto">
                        {title(item)}
                        {item.other_title && <> · {item.other_title}</>}
                      </strong>
                      {!item.briefing && <p className="personal-update-headline">{personalUpdate(item, settings, t).headline}</p>}
                      <details className="briefing-details">
                        <summary>{t("פרטי העדכון", "Update details")}</summary>
                        <p className="personal-update-reason">{personalUpdate(item, settings, t).reason}</p>
                        <p className="personal-update-source">{personalUpdate(item, settings, t).source}</p>
                      </details>
                      <span className="field-help">
                        {item.event_source && <>{({personal:t("יומן אישי","Personal calendar"),google:"Google Calendar",moodle:"Moodle",timetable:t("מערכת שעות","Class timetable")} as Record<string,string>)[item.event_source]??item.event_source} · </>}
                        {item.due && format(item.due)}
                        {item.start && format(item.start)}
                        {item.end && ` — ${format(item.end)}`}
                      </span>
                      {item.change_kind&&<p className="field-help">{item.change_kind==="added"?t("אירוע נוסף לייצוא.","An event was added to the export."):item.change_kind==="removed"?t("האירוע אינו בייצוא האחרון; אין בכך אישור לביטול.","The event is absent from the latest export; this does not confirm cancellation."):t("פרטי האירוע השתנו בייצוא.","Event details changed in the export.")}{item.previous_start&&<> {t("מועד קודם: ","Previous date: ")}{format(item.previous_start)}.</>}{item.observed_at&&<> {t("זוהה באפליקציה: ","Observed in LifeOS: ")}{format(new Date(item.observed_at*1000).toISOString())}</>}</p>}
                      {item.briefing && (
                        <BriefingSnapshotCard
                          snapshot={item.briefing}
                          settings={settings}
                          t={t}
                        />
                      )}
                      <div className="google-actions">
                        <Button
                          variant="secondary"
                          size="small"
                          onClick={() => {
                            setOpen(false);
                            onOpen(item);
                          }}
                        >
                          {t("פתיחת הפריט", "Open item")}
                        </Button>
                        {onDiscuss && item.kind !== "request_followup" && <Button size="small" variant="secondary" disabled={busy} onClick={() => void perform(async () => { await onDiscuss(item); setOpen(false); })}>{t("המשך עם העוזר", "Continue with assistant")}</Button>}
                        {!showHidden && !item.read && (
                          <Button
                            variant="ghost"
                            size="small"
                            disabled={busy}
                            aria-label={`${t("סימון כנקראה", "Mark as read")}: ${title(item)}`}
                            onClick={() =>
                              void perform(() => onRead([item.id]))
                            }
                          >
                            {t("סימון כנקראה", "Mark as read")}
                          </Button>
                        )}
                      </div>
                      {showHidden ? (
                        <div className="notification-hidden-actions">
                          <p className="field-help">
                            {item.dismissed
                              ? t("ההתראה הוסתרה", "Notification dismissed")
                              : item.snoozed_until
                                ? t("נדחתה עד ", "Snoozed until ") +
                                  format(
                                    new Date(
                                      item.snoozed_until * 1000,
                                    ).toISOString(),
                                  )
                                : ""}
                          </p>
                          <Button
                            size="small"
                            variant="secondary"
                            disabled={busy}
                            onClick={() =>
                              void act({ id: item.id, action: "restore" })
                            }
                          >
                            {t("החזרת ההתראה", "Restore notification")}
                          </Button>
                        </div>
                      ) : (
                        onAction && (
                          <details className="notification-extra">
                            <summary>
                              {t("פעולות נוספות", "More actions")}
                            </summary>
                            <form
                              className="notification-snooze"
                              onSubmit={(event) => {
                                event.preventDefault();
                                const minutes = Number(
                                  new FormData(event.currentTarget).get(
                                    "minutes",
                                  ),
                                ) as 15 | 60 | 1440;
                                void act({
                                  id: item.id,
                                  action: "snooze",
                                  minutes,
                                });
                              }}
                            >
                              <label>
                                {t("דחייה למשך", "Snooze for")}
                                <select
                                  name="minutes"
                                  aria-label={t("דחייה למשך", "Snooze for")}
                                  defaultValue="60"
                                >
                                  <option value="15">
                                    {t("15 דקות", "15 minutes")}
                                  </option>
                                  <option value="60">
                                    {t("שעה", "1 hour")}
                                  </option>
                                  <option value="1440">
                                    {t("24 שעות", "24 hours")}
                                  </option>
                                </select>
                              </label>
                              <Button
                                type="submit"
                                size="small"
                                variant="secondary"
                                disabled={busy}
                              >
                                {t("דחיית ההתראה", "Snooze")}
                              </Button>
                            </form>
                            <Button
                              size="small"
                              variant="ghost"
                              disabled={busy}
                              onClick={() =>
                                void act({ id: item.id, action: "dismiss" })
                              }
                            >
                              {t("הסתרת ההתראה", "Dismiss notification")}
                            </Button>
                          </details>
                        )
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {(showHidden ? data.hidden_truncated : data.truncated) && (
                <p className="field-help">
                  {t(
                    "מוצגות עד 20 התראות. סימון המוצגות לא מסמן פריטים נוספים.",
                    "Showing up to 20 notifications. Marking displayed items does not mark additional items.",
                  )}
                </p>
              )}
              <p className="field-help">
                {t(
                  "דחייה והסתרה משפיעות על ההתראה בלבד. דחייה תחזור ברענון לאחר הזמן שנבחר כשהאפליקציה פתוחה.",
                  "Snooze and dismiss affect only the notification. Snoozed items return on refresh after the selected time while the app is open.",
                )}
              </p>
              {data.conflicts_limited && (
                <p className="field-help">
                  {t(
                    "הבדיקה מוגבלת ל־20 התנגשויות; כדאי לבדוק גם ביומן.",
                    "Conflict detection is limited to 20; also check your calendar.",
                  )}
                </p>
              )}
              {csrf && (
                <BriefingScheduleSettings
                  csrf={csrf}
                  t={t}
                  onChanged={onRefresh}
                  onUnauthorized={onUnauthorized}
                />
              )}
              <section
                className="notification-browser"
                aria-label={t("התראות דפדפן", "Browser notifications")}
              >
                <h3>{t("התראות דפדפן", "Browser notifications")}</h3>
                <p className="field-help">
                  {t(
                    "בהפעלה שלך בלבד, כשהדף פתוח ברקע. מוצג טקסט כללי ללא כותרות אישיות; שעות שקטות נשמרות. זה אינו Push כשהאפליקציה סגורה.",
                    "Opt in for alerts while the page is open in the background. Only generic text is shown; quiet hours apply. This is not Push while the app is closed.",
                  )}
                </p>
                <p className="field-help">
                  {browser.status === "unsupported"
                    ? t(
                        "האפשרות אינה נתמכת בדפדפן או בהקשר הנוכחי.",
                        "Unavailable in this browser or context.",
                      )
                    : browser.status === "denied"
                      ? t(
                          "ההרשאה חסומה. אפשר לשנות אותה בהגדרות האתר בדפדפן.",
                          "Permission is blocked. Change it in your browser site settings.",
                        )
                      : browser.enabled
                        ? t("פעיל בדפדפן הזה", "Enabled in this browser")
                        : t("כבוי בדפדפן הזה", "Off in this browser")}
                </p>
                <div className="google-actions">
                  <Button
                    variant="secondary"
                    size="small"
                    disabled={
                      browser.busy ||
                      (!browser.opted &&
                        (browser.status === "unsupported" ||
                          browser.status === "denied" || browser.pushActive))
                    }
                    onClick={() => void browser.toggle()}
                  >
                    {browser.opted
                      ? t("כיבוי התראות דפדפן", "Disable browser notifications")
                      : t("הפעלת התראות דפדפן", "Enable browser notifications")}
                  </Button>
                  {browser.enabled && (
                    <Button
                      variant="ghost"
                      size="small"
                      disabled={browser.busy}
                      onClick={() => void browser.test()}
                    >
                      {t("שליחת התראת ניסיון", "Send test notification")}
                    </Button>
                  )}
                </div>
                {browser.error && (
                  <p role="alert" className="field-help">
                    {t(
                      "לא ניתן להציג או לשמור התראות דפדפן כרגע. מרכז ההתראות עדיין זמין.",
                      "Could not show or save browser notifications. The in-app center remains available.",
                    )}
                  </p>
                )}
              </section>
              <WebPushSettings csrf={csrf ?? ""} settings={settings} t={t} onUnauthorized={onUnauthorized} />
              {browser.pushActive && <p className="field-help">{t("Push פעיל בדפדפן הזה; כבו אותו כדי להשתמש בערוץ הדף הפתוח.", "Push is active in this browser; turn it off to use the open-page channel.")}</p>}
              <details className="notification-preferences">
                <summary>
                  <Settings2 size={15} aria-hidden="true" />
                  {t("העדפות התראות", "Notification preferences")}
                </summary>
                <form
                  className="form-stack"
                  onSubmit={save}
                  key={JSON.stringify(data.preferences)}
                >
                  {(
                    [
                      [
                        "enabled",
                        t("התראות בתוך האפליקציה", "In-app notifications"),
                      ],
                      [
                        "tasks",
                        t(
                          "מועדי משימות ואיחורים",
                          "Task deadlines and overdue work",
                        ),
                      ],
                      ["events", t("אירועים מתקרבים ועדכוני Moodle · באפליקציה בלבד", "Upcoming events and Moodle updates · in-app only")],
                      ["mail", t("מיילים רלוונטיים חדשים · באפליקציה בלבד", "New relevant mail · in-app only")],
                    ["conflicts", t("התנגשויות ביומן", "Calendar conflicts")],
                      [
                        "briefings",
                        t("התראות סיכום מתוזמן", "Scheduled briefing alerts"),
                      ],
                      ["quiet_enabled", t("שעות שקטות", "Quiet hours")],
                    ] as const
                  ).map(([name, text]) => (
                    <label className="notification-check" key={name}>
                      <input
                        type="checkbox"
                        name={name}
                        defaultChecked={data.preferences[name]}
                      />
                      {text}
                    </label>
                  ))}
                  <div className="form-grid">
                    <label>
                      {t("תחילת שעות שקטות", "Quiet hours start")}
                      <input
                        type="time"
                        name="quiet_start"
                        required
                        defaultValue={data.preferences.quiet_start}
                      />
                    </label>
                    <label>
                      {t("סיום שעות שקטות", "Quiet hours end")}
                      <input
                        type="time"
                        name="quiet_end"
                        required
                        defaultValue={data.preferences.quiet_end}
                      />
                    </label>
                  </div>
                  <p className="field-help">
                    {t(
                      "לפי אזור הזמן בהגדרות. שעות זהות משתיקות את המונה והתראות הדפדפן האוטומטיות לאורך כל היום.",
                      "Uses your workspace timezone. Equal times silence the badge and automatic browser alerts all day.",
                    )}
                  </p>
                  <Button type="submit" disabled={busy}>
                    {t("שמירת העדפות", "Save preferences")}
                  </Button>
                </form>
              </details>
            </>
          )}
        </Modal>
      )}
    </>
  );
}
