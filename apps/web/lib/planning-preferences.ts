export const ALL_WEEKDAYS = [1,2,3,4,5,6,7];
export const WEEKDAYS = [
  {value:7,he:"ראשון",en:"Sunday"},{value:1,he:"שני",en:"Monday"},{value:2,he:"שלישי",en:"Tuesday"},
  {value:3,he:"רביעי",en:"Wednesday"},{value:4,he:"חמישי",en:"Thursday"},{value:5,he:"שישי",en:"Friday"},{value:6,he:"שבת",en:"Saturday"},
];
export type PlanningDefaults = { duration: number; days: number; window_start: string; window_end: string; weekdays:number[]; daily_limit_minutes?:number|null };
export type PlanningPreferences = Omit<PlanningDefaults,"weekdays"> & {weekdays?:number[]; enabled: boolean; assistant_enabled?: boolean; revision: number };
export const DEFAULT_PLANNING: PlanningDefaults = { duration: 30, days: 1, window_start: '08:00', window_end: '20:00',weekdays:[...ALL_WEEKDAYS] };
export function planningDefaults(value: PlanningPreferences): PlanningDefaults {
  if (!value.enabled) return { ...DEFAULT_PLANNING,weekdays:[...ALL_WEEKDAYS] };
  const { duration, days, window_start, window_end } = value;
  return { duration, days, window_start, window_end,weekdays:[...(value.weekdays??ALL_WEEKDAYS)],...(value.daily_limit_minutes!=null?{daily_limit_minutes:value.daily_limit_minutes}:{}) };
}
export function weekdayNames(values:number[],language:string){return WEEKDAYS.filter(day=>values.includes(day.value)).map(day=>language==='he'?day.he:day.en).join(', ');}
