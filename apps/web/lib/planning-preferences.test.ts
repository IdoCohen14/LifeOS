import { describe, expect, it } from 'vitest';
import { planningDefaults } from './planning-preferences';

describe('explicit planning defaults', () => {
  it('uses built-in values while saved preferences are off', () => {
    expect(planningDefaults({ enabled: false, duration: 60, days: 3, window_start: '09:00', window_end: '17:00', revision: 1 })).toEqual({ duration: 30, days: 1, window_start: '08:00', window_end: '20:00', weekdays: [1,2,3,4,5,6,7] });
  });
  it('uses only the explicit operational fields when enabled', () => {
    expect(planningDefaults({ enabled: true, daily_limit_minutes:120, duration: 45, days: 2, window_start: '10:00', window_end: '16:00', revision: 9 })).toEqual({ daily_limit_minutes:120, duration: 45, days: 2, window_start: '10:00', window_end: '16:00', weekdays: [1,2,3,4,5,6,7] });
  });
});

it('prefills chosen weekdays without aliasing the saved list',()=>{
 const saved={enabled:true,duration:45,days:7,window_start:'09:00',window_end:'17:00',revision:2,weekdays:[1,3,7]};
 const defaults=planningDefaults(saved);
 expect(defaults.weekdays).toEqual([1,3,7]);
 defaults.weekdays.push(2);
 expect(saved.weekdays).toEqual([1,3,7]);
});
