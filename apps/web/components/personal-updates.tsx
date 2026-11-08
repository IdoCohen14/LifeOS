"use client";

import { useState } from "react";
import { ArrowUpLeft, Bell, Check, Clock3 } from "lucide-react";
import { ApiError } from "@/lib/api";
import { personalUpdate } from "@/lib/personal-update";
import type { Settings, Translate } from "@/lib/types";
import type { NotificationAction, NotificationFeed, NotificationItem } from "./notification-center";
import { Button } from "./ui/button";

export function PersonalUpdates({ data, settings, now, t, disabled = false, onOpen, onShowAll, onRead, onAction, onRefresh, onUnauthorized, onDiscuss }: {
  data: NotificationFeed | null; settings: Settings; now: Date; t: Translate; disabled?: boolean;
  onOpen: (item: NotificationItem) => void; onShowAll: () => void;
  onRead: (ids: string[]) => Promise<void>; onAction: (action: NotificationAction) => Promise<void>;
  onRefresh: () => Promise<void>; onUnauthorized: () => void;
  onDiscuss?: (item: NotificationItem) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const unread = data?.items.filter(item => !item.read && !item.dismissed && (!item.snoozed_until || item.snoozed_until * 1000 <= now.getTime())) || [];
  const item = data?.preferences.enabled ? unread[0] : undefined;
  const copy = item ? personalUpdate(item, settings, t) : null;
  async function perform(action: () => Promise<void>) {
    if (busy || disabled) return;
    setBusy(true); setError("");
    try { await action(); }
    catch (error) {
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      setError(t("הפעולה לא נשמרה. אפשר לרענן ולנסות שוב.", "The action was not saved. Refresh and try again."));
    } finally { setBusy(false); }
  }
  return <section className="personal-updates panel" aria-label={t("העדכונים שלי", "My updates")}>
    <div className="personal-updates-heading"><div><span className="personal-updates-icon"><Bell size={18} aria-hidden="true" /></span><h2>{t("מה כדאי לדעת", "Worth knowing")}</h2></div>
      <Button variant="ghost" size="small" onClick={onShowAll}>{t("כל העדכונים", "All updates")}<ArrowUpLeft size={15} aria-hidden="true" /></Button></div>
    {(disabled || !!data?.stale_sources.length) && <p className="field-help" role="status">{t("חלק מהמידע עשוי להיות לא מעודכן. כדאי לבדוק את החיבורים לפני שינוי התכנון.", "Some information may be outdated. Check connections before changing your plans.")}{data?.stale_sources.length ? ` ${data.stale_sources.join(", ")}` : ""}</p>}
    {item && copy ? <article className="personal-update-card">
      <p className="personal-update-headline">{copy.headline}</p><h3 dir="auto">{copy.subject}{item.other_title && ` · ${item.other_title}`}</h3>
      {copy.context && <p className="personal-update-date"><bdi>{copy.context}</bdi></p>}
      <details className="personal-update-details"><summary>{t("פרטי העדכון", "Update details")}</summary><p className="personal-update-reason">{copy.reason}</p><p className="personal-update-source">{copy.source}</p></details>
      <div className="personal-update-actions"><Button variant="secondary" onClick={() => onOpen(item)}>{copy.action}<ArrowUpLeft size={15} aria-hidden="true" /></Button>
        <Button variant="ghost" disabled={busy || disabled} onClick={() => void perform(() => onRead([item.id]))}><Check size={15} aria-hidden="true" />{t("ראיתי", "Seen")}</Button>
        <details className="calm-update-actions"><summary>{t("עוד", "More")}</summary><div>{onDiscuss && item.kind !== "request_followup" && <Button variant="secondary" disabled={busy || disabled} onClick={() => void perform(() => onDiscuss(item))}>{t("המשך עם העוזר", "Continue with assistant")}</Button>}<Button variant="ghost" disabled={busy || disabled} onClick={() => void perform(() => onAction({ id: item.id, action: "snooze", minutes: 60 }))}><Clock3 size={15} aria-hidden="true" />{t("בעוד שעה", "In an hour")}</Button></div></details></div>
      {unread.length > 1 && <p className="field-help">{t(`עוד ${unread.length - 1} עדכונים בתיבה`, `${unread.length - 1} more updates in your inbox`)}{data?.truncated ? t(" · הרשימה חלקית", " · Partial list") : ""}</p>}
    </article> : <p className="personal-update-empty">{!data ? t("העדכונים לא נטענו כרגע.", "Updates could not be loaded right now.") : !data.preferences.enabled ? t("העדכונים כבויים כרגע. אפשר לשנות זאת בהעדפות התיבה.", "Updates are off. You can change this in inbox preferences.") : t("אין עדכונים חדשים כרגע. אפשר להתמקד במה שתכננת.", "No new updates right now. You can focus on your plans.")}</p>}
    {!data && <Button variant="ghost" disabled={busy || disabled} onClick={() => void perform(onRefresh)}>{t("ניסיון נוסף", "Try again")}</Button>}
    {error && <p role="alert" className="error-message">{error}</p>}
  </section>;
}
