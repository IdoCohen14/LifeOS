"""Curated operational instructions, never model output or personal records."""

from typing import Literal

HelpTopic = Literal[
    "academic_courses",
    "academic_timetable",
    "academic_deadlines",
    "tasks",
    "calendar",
    "google",
    "gmail",
    "moodle",
    "privacy",
    "planning",
    "preferences",
    "briefings",
    "weekly_review",
    "notifications",
    "push",
    "history",
    "backups",
    "recurrence",
]

HELP = {
    "academic_courses": (
        "במרחב האקדמי פתחו ״הקורסים שלי״ ובחרו קורס. המטלות הפתוחות יופיעו תחילה. פרטי הקורס וההתקדמות נפתחים לפי בקשה. להזנה ידנית פתחו ״אפשרויות ידניות נוספות״; קורס שנוסף כאן אינו נרשם במכללה.",
        "In Academic hub, open My courses and choose a course. Open assignments appear first; expand Course details and progress when needed. For manual entry, open Additional manual options. Adding a course here does not enroll you at the institution.",
    ),
    "academic_timetable": (
        "פתחו ״מערכת השעות שלי״ בתפריט. בטלפון בוחרים יום; לחיצה על שיעור מציגה את פרטי המקור והחדר. להזנה ידנית: המרחב האקדמי ← אפשרויות ידניות נוספות ← הוספת מפגשים שבועיים. בדקו שעות, סמסטר ומיקום לפני אישור; אין זיהוי אוטומטי של חגים או ביטולים.",
        "Open My timetable from the menu. On your phone choose a day; tap a class for its source details and room. For manual entry: Academic hub → Additional manual options → Add weekly meetings. Review hours, term and location before confirming; holidays and cancellations are not inferred.",
    ),
    "academic_deadlines": (
        "במרחב האקדמי מוצגות קודם מטלות ומבחנים פתוחים, לפי מועד. ״סינון״ מציג סוג, תקופה והשלמה; ״הצגת נוספים״ ממשיך את הרשימה. ״תכנון זמן״ פותח את המשימה המקושרת, ושמירת זמן ביומן דורשת אישור. סימון בוצע אינו מגיש מטלה במכללה. אין עזרה בפתרון שיעורי בית.",
        "Academic hub starts with open assignments and exams ordered by deadline. Filter reveals type, period and completion; Show more continues the list. Plan time opens the linked task and saving a calendar block needs confirmation. Marking complete does not submit work to your institution. Homework solutions are outside the assistant’s scope.",
    ),
    "tasks": (
        "ב״המשימות שלי״ מוצגות תחילה משימות פתוחות. להוספה לחצו ״משימה חדשה״ והזינו כותרת ותאריך. עדיפות, שעה מדויקת והערה נפתחות לפי צורך. שלוש הנקודות ליד משימה פותחות עריכה ומחיקה; תיבת הסימון מסמנת השלמה.",
        "My tasks starts with open tasks. Choose New task and enter a title and date. Expand priority, exact time or a note only when needed. The three dots beside a task reveal edit and delete; its checkbox marks completion.",
    ),
    "calendar": (
        "ב'היומן שלי' לחצו 'אירוע חדש'. אירועים מיובאים נערכים רק דרך קישור המקור.",
        "In My Calendar, choose New event. Edit imported events through their source link.",
    ),
    "google": (
        "הגדרות ← החיבורים שלי ← Google Calendar. כאן מתחברים, בוחרים יומנים ומבקשים סנכרון. אירוע מיובא נערך דרך המקור.",
        "Settings → My connections → Google Calendar. Connect, select calendars and request synchronization. Edit imported events at their source.",
    ),
    "gmail": (
        "הגדרות ← החיבורים שלי ← Gmail. המיילים הרלוונטיים מופיעים ב״היום שלי״, הודעה אחת בכל פעם. מענה פותח Gmail; דילוג וסימון כנקרא כאן משנים את תור LifeOS בלבד.",
        "Settings → My connections → Gmail. Relevant messages appear one at a time in My day. Reply opens Gmail; skipping or marking read here only updates the LifeOS queue.",
    ),
    "moodle": (
        "הגדרות ← החיבורים שלי ← Moodle. חברו קישור מנוי מורשה וסנכרנו. מוצג רק מידע שהמקור מפרסם; אין להסיק שהיעלמות מטלה פירושה ביטול או הגשה. אין לשלוח קישור מנוי או מפתח בצ׳אט.",
        "Settings → My connections → Moodle. Connect an authorized subscription and sync. Only published source data is available; a missing assignment does not prove cancellation or submission. Do not share subscription links or keys in chat.",
    ),
    "privacy": (
        "עזרה מובנית מציגה הוראות בלי להפעיל מודל. בקשות שיחה משתמשות במודל מקומי; שמירת "
        "משימות ואירועים דורשת אישור. אין שליחת מייל או שינוי יומן חיצוני. חיבורי ספקים "
        "ו־Push משתמשים בשירותים חיצוניים רק בהפעלה והרשאה שלך. נתונים אישיים וגיבויים נשמרים "
        "במחשב.",
        "Built-in help shows instructions without a model. Chat uses local inference; saving "
        "tasks/events needs confirmation. No email sending or external calendar mutation. "
        "Provider connections and Push use external services only after your setup/consent. "
        "Personal data and backups stay on this computer.",
    ),
    "planning": (
        "היום שלי ← תכנון, סיכומים וחיבורים ← למצוא זמן למשימות. בחרו משימה, משך וטווח; בדקו את ההצעה ואשרו שמירה. אין צורך במודל, והפעולה אינה משלימה משימה או משנה את מועד ההגשה.",
        "My day → Planning, reviews and connections → Make time for tasks. Choose a task, duration and period; review and confirm the proposal. No model is needed, and this does not complete the task or change its deadline.",
    ),
    "preferences": (
        "הגדרות ← העדפות תכנון ← הצגה ועריכת העדפות. בחרו שעות, ימים, משך וטווח והפעילו שימוש בהעדפות. אפשר לשנות כל הצעה לפני אישור; יום שלא נבחר אינו מוחלף בשקט ביום אחר. השעות לפי אזור הזמן הנוכחי ותקרת דקות סופרת זמן מתוזמן, לא זמן למידה שנמדד.",
        "Settings → Planning preferences → View and edit preferences. Choose hours, weekdays, duration and search period, then enable their use. Each proposal stays editable before confirmation; an excluded day is not silently replaced. Hours use your current timezone and the daily minute limit counts scheduled time, not measured study.",
    ),
    "briefings": (
        "היום שלי ← תכנון, סיכומים וחיבורים ← מבט יומי ושבועי. בחרו היום או 7 ימים. הסיכום מבוסס על היומן והמשימות השמורים; הוא אינו מודד זמן למידה בפועל. התראות סיכום מתוזמנות דורשות הפעלה נפרדת.",
        "My day → Planning, reviews and connections → Day and week overview. Choose Today or 7 days. Summaries use saved calendar entries and tasks, not measured study time. Scheduled briefing notifications require separate opt-in.",
    ),
    "weekly_review": (
        "היום שלי ← תכנון, סיכומים וחיבורים ← איך עבר השבוע. מוצגים שינויים שנרשמו; היסטוריה חסרה אינה משוחזרת או מנוחשת.",
        "My day → Planning, reviews and connections → Weekly review. It shows recorded changes; missing history is not reconstructed or guessed.",
    ),
    "notifications": (
        "פתחו את הפעמון. אפשר לסמן נקראה, לדחות או להסתיר התראה ולשחזר מוסתרות. פתיחת "
        "הרשימה אינה מסמנת נקראה. בהעדפות בוחרים קטגוריות ושעות שקטות לפי אזור הזמן. "
        "מרכז ההתראות אינו משנה את המשימה או את היומן המקורי. מיילים ואירועים מתקרבים עם "
        "עדכוני Moodle דורשים הפעלה נפרדת ומוצגים בתוך האפליקציה בלבד. סימון התראת מייל "
        "כנקראה אינו מעביר את המייל בתור המיילים.",
        "Open the bell to mark read, snooze, dismiss or restore hidden notices. Opening "
        "the list does not mark items read. Preferences control categories/quiet hours "
        "in the workspace timezone. This does not change source tasks or calendar "
        "records. Mail and upcoming calendar/Moodle change notices require separate opt-in "
        "and appear only inside the app. Marking a mail notification read does not review "
        "that message in the mail queue.",
    ),
    "push": (
        "פתחו את הפעמון ואת הגדרות Push. באייפון פותחים את האתר הפרטי ב־Safari, מוסיפים למסך הבית ופותחים מהאייקון לפני מתן הרשאה. המחשב ו־Tailscale צריכים לפעול. ההודעה כללית; שעות שקטות נבדקות במחשב, והשתקה באייפון דרך Focus. המסירה אינה מובטחת.",
        "Open the bell and Push settings. On iPhone, open the private site in Safari, add it to the Home Screen and open its icon before granting permission. The computer and Tailscale must run. Messages are generic; quiet hours are checked on the host and iPhone silencing uses Focus. Delivery is not guaranteed.",
    ),
    "history": (
        "בעוזר פתחו ״היסטוריית שיחה מקומית״. שמירה כבויה כברירת מחדל; בהפעלה נשמר טקסט "
        "עד 30 יום ועד 200 חילופי הודעות, ונטענים 50 האחרונים. כיבוי אינו מוחק טקסט קיים; ״מחיקת ההיסטוריה״ "
        "דורשת אישור. הצעות ישנות אינן ניתנות לאישור מתוך ההיסטוריה, וגיבויים קודמים עשויים "
        "להכיל טקסט שנמחק.",
        "Open Local conversation history in the assistant. Saving is off by default; opt in "
        "for up to 30 days and 200 exchanges, loading the latest 50. Off does not delete existing text; "
        "Clear saved history needs confirmation. Old proposals cannot be approved from "
        "history, and older backups may retain deleted text.",
    ),
    "backups": (
        "הגדרות ← גיבוי ושחזור. בחשבון אישי יוצרים גיבוי מוצפן בסיסמה נפרדת. ״בדיקה ושחזור״ מאפשר לסקור גיבוי; המידע משתנה רק אחרי אישור שחזור מפורש. חיבורים חיצוניים ומכשירי התראות דורשים חיבור מחדש לאחר שחזור חשבון. שחזור התקנה מלאה נעשה בנפרד כשהאתר סגור, דרך Restore-LifeOS.cmd.",
        "Settings → Backup and restore. In a personal account, create an encrypted backup with a separate password. Review and restore previews an archive; data changes only after explicit restore confirmation. Provider connections and notification devices need reconnection after account restore. Full-installation recovery is separate, with LifeOS stopped, through Restore-LifeOS.cmd.",
    ),
    "recurrence": (
        "ביומן בחרו ״אירוע שבועי חוזר״ כדי לבדוק ולאשר 2–52 מופעים מקומיים. אותה שעה מקומית "
        "נשמרת; שעות חסרות או כפולות נדחות. ב״ניהול סדרות שבועיות״ בוחרים מופעים למחיקה "
        "מתאריך מסוים ובודקים רשימה לפני אישור. מופעים שנערכו או שמצבם אינו ידוע מוגנים "
        "כברירת מחדל. אפשר גם לבחור שינוי שעות, שעה ומשך חדשים למופעים עתידיים עם שעה. "
        "בדקו את השעות הקיימות והחדשות לפני אישור; אירועי יום שלם נשארים ללא שינוי "
        "וייתכנו חפיפות. בשינוי שעות התאריכים והתוכן נשמרים. ״הזזת תאריכים״ מאפשרת "
        "הזזה של עד 28 ימים קדימה או אחורה, עם שמירת שעת ההתחלה והמשך לכל מופע. "
        "בהזזת תאריכים אפשר לסמן במפורש ״לכלול אירועי יום שלם״; מספר הימים נשמר, "
        "והתצוגה מציגה את היום האחרון הכלול. יעד לפני היום נדחה. "
        "לכותרות בחרו ״שינוי כותרות״ והזינו כותרת חדשה למופעים שבחרתם; שם הסדרה המקורי "
        "נשאר לזיהוי. ״שינוי סוג אירוע״ ממיר מופעים של יום אחד בין יום שלם לשעה, אחרי בחירת "
        "סוג ובדיקת הטווחים; מופעים של כמה ימים ידולגו. משך ההמרה בדקות בפועל. ״תאריך ושעה יחד״ משנה מופעים עם שעה בהצעה אחת, "
        "עם מספר ימים, שעה חדשה ומשך בפועל; נדרש אישור נפרד. בדקו את הכותרות והמועדים לפני אישור. אין חזרה אינסופית.",
        "In My Calendar, choose Weekly recurring event to review and confirm 2–52 local "
        "occurrences. Local clock is preserved; missing/repeated times are rejected. "
        "Manage weekly series previews date-forward deletions before separate "
        "confirmation. Edited/unknown occurrences are protected by default. Choose Change "
        "times to review a new clock and duration for future timed occurrences; dates and "
        "content are preserved. All-day entries stay unchanged; other events may overlap. "
        "Shift dates moves timed occurrences by up to28local calendar days in either "
        "direction, preserving each local start clock and elapsed duration. "
        "Explicitly select Include all-day occurrences to shift date-only ranges while preserving "
        "their calendar-day length; the preview shows the last included day. Destinations before "
        "today are rejected. Review all current/new dates and times before approval. "
        "Choose Change titles to review a new title for selected occurrences; the original "
        "series label stays for identification. Change event type converts single-day sources "
        "between all-day and timed after explicit type/range review; multi-day sources are skipped. "
        "Conversion duration uses elapsed minutes. Shift dates and times separately reviews "
        "a day shift, new clock and elapsed duration together for timed occurrences. Endless recurrence is not supported.",
    ),
}

LABELS = {
    "academic_courses": ("סמסטרים והזנת קורסים", "Terms and course entry"),
    "academic_timetable": ("מערכת שעות שבועית", "Weekly class timetable"),
    "academic_deadlines": ("מטלות, מבחנים ותכנון זמן", "Deadlines and time planning"),
    "tasks": ("משימות", "Tasks"),
    "calendar": ("יומן אישי", "Personal calendar"),
    "google": ("חיבור Google Calendar", "Google Calendar connection"),
    "gmail": ("דואר Gmail", "Gmail inbox"),
    "moodle": ("יומן Moodle", "Moodle calendar"),
    "privacy": ("פרטיות והרשאות", "Privacy and consent"),
    "planning": ("הקצאת זמן למשימה", "Task time blocks"),
    "preferences": ("העדפות תכנון", "Planning preferences"),
    "briefings": ("סיכומים יומיים ושבועיים", "Daily and weekly briefings"),
    "weekly_review": ("סקירת ביצוע שבועית", "Weekly completion review"),
    "notifications": ("מרכז התראות ושעות שקטות", "Notifications and quiet hours"),
    "push": ("Push בדפדפן", "Browser Push"),
    "history": ("היסטוריית שיחות", "Conversation history"),
    "backups": ("גיבוי, בדיקה ושחזור", "Backup, inspection and restore"),
    "recurrence": ("אירועים וסדרות שבועיות", "Weekly events and series"),
}


def catalog():
    return {
        "source": "built_in",
        "topics": [
            {"id": key, "label": LABELS[key], "answer": value} for key, value in HELP.items()
        ],
    }
