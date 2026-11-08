import { expect, it } from 'vitest';
import { personalUpdate } from './personal-update';
import type { NotificationItem } from '@/components/notification-center';
const t=(he:string)=>he;
const settings={display_name:'',language:'he' as const,theme:'dark' as const,timezone:'Asia/Jerusalem'};
const base:NotificationItem={id:'a',kind:'due_soon',title:'מטלה 1',target:'tasks',source_ids:['task'],read:false,academic_kind:'assignment',due:'2026-11-04',course_name:'מערכות הפעלה'};
it('describes a request follow-up without claiming task completion or source sync',()=>{
 const copy=personalUpdate({...base,kind:'request_followup',observed_at:1793760000},settings,t);
 expect(copy.headline).toBe('זמן לחזור לבקשה');
 expect(copy.source).toContain('הבקשות שלך');
 expect(copy.source).not.toContain('סנכרון');
 expect(copy.subject).toContain('מערכות הפעלה');
});
it('explains a deadline with course and date-only context without inventing hours',()=>{
 const copy=personalUpdate(base,settings,t);
 expect(copy.subject).toBe('מטלה 1 · מערכות הפעלה');
 expect(copy.context).toContain('04/11/2026');
 expect(copy.reason).toBeTruthy();
 expect(copy.action).toBe('פתיחת המטלה');
 expect(copy.context).not.toContain('00:00');
});
it('does not claim feed disappearance means cancellation',()=>{
 const copy=personalUpdate({...base,kind:'moodle_update',change_kind:'removed',due:undefined},settings,t);
 expect(copy.reason).toContain('אין אישור לביטול');
});
it('describes added and changed source observations without pretending to submit work',()=>{
 expect(personalUpdate({...base,kind:'moodle_update',change_kind:'added'},settings,t).headline).toBe('נוסף מועד ב־Moodle');
 expect(personalUpdate({...base,kind:'moodle_update',change_kind:'changed'},settings,t).headline).toBe('מועד עודכן');
});
it('keeps exam and ordinary task language distinct from assignments',()=>{
 expect(personalUpdate({...base,academic_kind:'exam'},settings,t).headline).toBe('מבחן מתקרב');
 expect(personalUpdate({...base,academic_kind:undefined},settings,t).action).toBe('פתיחת המשימה');
});
