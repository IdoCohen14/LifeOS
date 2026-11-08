import { ALL_WEEKDAYS, WEEKDAYS } from "@/lib/planning-preferences";
import type { Translate } from "@/lib/types";
export function WeekdayPicker({defaultValue=ALL_WEEKDAYS,t}:{defaultValue?:number[];t:Translate}){
 return <fieldset className="weekday-picker"><legend>{t("ימי תכנון","Planning weekdays")}</legend>{WEEKDAYS.map(day=><label className="notification-check" key={day.value}><input type="checkbox" name="weekdays" value={day.value} defaultChecked={defaultValue.includes(day.value)} />{t(day.he,day.en)}</label>)}</fieldset>;
}
