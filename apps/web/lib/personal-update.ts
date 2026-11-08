import type { NotificationItem } from "@/components/notification-center";
import type { Settings, Translate } from "./types";

export function personalUpdate(item: NotificationItem, settings: Settings, t: Translate) {
  const format = (value: string) => value.length === 10
    ? value.split("-").reverse().join("/")
    : new Intl.DateTimeFormat(settings.language, { dateStyle: "short", timeStyle: "short", timeZone: settings.timezone }).format(new Date(value));
  const assignment = item.kind === "moodle_update"
    ? item.title.match(/^יש להגיש את ['"](.+)['"]$/)?.[1]
      ?? item.title.match(/^(.+) (?:is due(?: \(extension\))?|\(Due date\))$/)?.[1]
    : undefined;
  const name = assignment || item.title || t("עדכון חדש", "New update");
  const isExam = item.academic_kind === "exam";
  const isAssignment = item.academic_kind === "assignment";
  const openTask = isExam ? t("פתיחת המבחן", "Open exam") : isAssignment ? t("פתיחת המטלה", "Open assignment") : t("פתיחת המשימה", "Open task");
  const subject = item.course_name && !name.includes(item.course_name) ? `${name} · ${item.course_name}` : name;
  const copy = item.lesson
    ? [t("השיעור הבא", "Next class"), [item.class_room ? `${t("כיתה", "Room")} ${item.class_room}` : t("כיתה לא צוינה במקור", "Room not provided by source"), item.instructor || t("מרצה לא צוין במקור", "Lecturer not provided by source")].join(" · "), t("פתיחת מערכת השעות", "Open timetable")]
    : item.kind === "request_followup"
    ? [t("זמן לחזור לבקשה", "Time to revisit a request"), t("התזכורת שבחרת הגיעה. אפשר להמשיך מההקשר השמור.", "Your follow-up is due. Continue from its saved reference."), t("חזרה לבקשה", "Return to request")]
    : item.kind === "conflict"
    ? [t("שני דברים באותו הזמן", "Two things at the same time"), t("כדאי לבדוק את החפיפה לפני שמוסיפים תוכניות נוספות.", "Review the overlap before adding more plans."), t("בדיקת היומן", "Review calendar")]
    : item.kind === "overdue"
      ? [t("המועד השמור עבר", "The saved deadline has passed"), t("המועד השמור עבר. אפשר לבדוק מה נשאר ולעדכן את הצעד הבא.", "The saved deadline has passed. Review what remains and choose your next step."), openTask]
      : item.kind === "due_soon"
        ? [isExam ? t("מבחן מתקרב", "An exam is approaching") : isAssignment ? t("מועד הגשה מתקרב", "An assignment deadline is approaching") : t("מועד מתקרב", "A deadline is approaching"), isAssignment ? t("כדאי לפנות זמן לעבודה לפני ההגשה.", "Make room to work before the deadline.") : t("כדאי לבדוק שפינית זמן לקראת המועד.", "Make sure you have time ahead of this date."), openTask]
        : item.kind === "moodle_update"
          ? [item.change_kind === "added" ? assignment ? t("נוספה מטלה", "Assignment added") : t("נוסף מועד ב־Moodle", "Moodle deadline added") : item.change_kind === "removed" ? t("שינוי במקור המידע", "Source information changed") : t("מועד עודכן", "A deadline changed"),
            item.change_kind === "removed" ? t("הפריט אינו בייצוא האחרון; אין אישור לביטול.", "The item is absent from the latest export; cancellation is not confirmed.") : item.change_kind === "added" ? t("נוסף פריט במקור. כדאי לבדוק את המועד והפרטים.", "A source item was added. Review its date and details.") : t("הפרטים במקור השתנו. כדאי לבדוק אם התכנון שלך צריך להשתנות.", "Source details changed. Check whether your plans need adjusting."), t("בדיקת המועד", "Review deadline")]
          : item.kind === "new_mail"
            ? [t("מייל שמחכה לך", "An email is waiting"), t("הודעה שעברה את הסינון שלך זמינה לעיון. לא נשלחה תשובה.", "A message matching your filters is ready to review. No reply has been sent."), t("פתיחת המיילים", "Open mail")]
            : item.kind === "upcoming_event"
              ? [t("אירוע מתקרב", "An event is coming up"), t("אפשר לבדוק את פרטי האירוע ולוודא שפינית לו זמן.", "Review the event details and make sure you have room for it."), t("פתיחת האירוע", "Open event")]
              : [item.kind === "weekly_briefing" ? t("המבט השבועי מוכן", "Your weekly overview is ready") : t("המבט היומי מוכן", "Your daily overview is ready"), t("תמונת מצב מהמשימות ומהיומן השמורים שלך.", "An overview of your saved tasks and calendar."), t("פתיחת הסיכום", "Open overview")];
  const source = item.kind === "request_followup" ? t("הבקשות שלך", "Your requests") : item.kind === "moodle_update" ? "Moodle" : item.kind === "new_mail" ? "Gmail"
    : ({ google: "Google Calendar", braude: t("תחנת המידע", "Student portal"), moodle: "Moodle", personal: t("היומן שלך", "Your calendar"), timetable: t("מערכת השעות", "Class timetable"), assignment: t("המטלות שלך", "Your assignments"), exam: t("המבחנים שלך", "Your exams") } as Record<string, string>)[item.event_source || ""]
      || t("המידע השמור שלך", "Your saved information");
  const date = item.due || item.start;
  const context = [date ? format(date) + (item.end ? ` – ${format(item.end)}` : "") : "", item.previous_start ? `${t("מועד קודם", "Previously")}: ${format(item.previous_start)}` : ""].filter(Boolean).join(" · ");
  const timestamp = item.source_updated_at ? `${t("סנכרון מקור", "Source synced")}: ${format(new Date(item.source_updated_at * 1000).toISOString())}`
    : item.observed_at ? `${item.kind === "request_followup" ? t("מועד לחזרה", "Follow-up time") : t("זוהה", "Observed")}: ${format(new Date(item.observed_at * 1000).toISOString())}` : "";
  return { headline: copy[0], reason: copy[1], action: copy[2], subject, context, source: [source, timestamp].filter(Boolean).join(" · ") };
}
