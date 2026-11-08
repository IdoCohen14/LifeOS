import { formatDay, shiftDay } from "@/lib/dates";
import type { Settings, Translate } from "@/lib/types";
import type { BriefingSnapshot } from "./notification-center";

export function BriefingSnapshotCard({
  snapshot,
  settings,
  t,
}: {
  snapshot: BriefingSnapshot;
  settings: Settings;
  t: Translate;
}) {
  const minutes = Math.round(snapshot.minutes);
  const duration = `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
  const generated = new Intl.DateTimeFormat(settings.language, {
    timeZone: snapshot.timezone,
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(snapshot.generated_at));
  const day = (value: string) =>
    formatDay(value, settings.language, { day: "numeric", month: "short" });
  return (
    <div className="notification-snapshot">
      <p className="briefing-essential">
        <span>{snapshot.events} {t("ביומן", "calendar entries")}</span>
        <span>{snapshot.deadlines} {t("מועדים", "deadlines")}</span>
        {snapshot.overdue > 0 && <span>{snapshot.overdue} {t("באיחור", "overdue")}</span>}
      </p>
      {snapshot.stale_sources.length > 0 && (
        <p className="planning-warning" role="status">{t("חלק מהמידע לא היה מעודכן בעת ההפקה", "Some data was outdated when generated")}: {snapshot.stale_sources.join(", ")}</p>
      )}
      <details className="briefing-details">
        <summary>{t("פרטי הסיכום השמור", "Saved briefing details")}</summary>
      <p className="field-help">{t("נכון ל־", "As of ")}{generated} · {snapshot.timezone}</p>
      <dl>
        <div>
          <dt>{t("פריטי יומן", "Calendar entries")}</dt>
          <dd>{snapshot.events}</dd>
        </div>
        <div>
          <dt>{t("מועדים לפניך", "Upcoming deadlines")}</dt>
          <dd>{snapshot.deadlines}</dd>
        </div>
        <div>
          <dt>{t("באיחור", "Overdue")}</dt>
          <dd>{snapshot.overdue}</dd>
        </div>
        <div>
          <dt>{t("משך ביומן · שעות:דקות", "Booked time · hours:minutes")}</dt>
          <dd>
            <bdi dir="ltr">{duration}</bdi>
          </dd>
        </div>
      </dl>
      <p className="field-help">
        {snapshot.all_day} {t("פריטים של יום שלם", "all-day entries")} ·{" "}
        {snapshot.undated} {t("משימות ללא מועד", "undated tasks")}
      </p>
      <p className="field-help">
        {day(snapshot.range_start)} — {day(shiftDay(snapshot.range_end, -1))} ·{" "}
        {t(
          "הזמן אינו כולל ימים שלמים או מאמץ למשימות. פתיחת הפריט מציגה תכנון עדכני.",
          "Booked time excludes all-day items and task effort. Open the item for current planning.",
        )}
      </p>
      </details>
    </div>
  );
}
