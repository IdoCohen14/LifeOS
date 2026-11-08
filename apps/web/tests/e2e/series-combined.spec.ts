import {test,expect} from '@playwright/test';
import {BASE,prepareFixtures} from './helpers';
import {dayKey,shiftDay} from '../../lib/dates';
test.beforeEach(async({playwright})=>prepareFixtures(playwright));
test('combined date and clock changes need one explicit reviewed approval',async({page})=>{
 await page.goto('/?view=calendar');await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');await page.getByRole('button',{name:'כניסה למרחב שלך'}).click();
 await expect(page.getByRole('button',{name:'ניהול סדרות שבועיות',exact:true})).toBeVisible();
 const session=await(await page.request.get('/api/session')).json();expect(session.test_mode).toBe(true);const headers={Origin:BASE,'X-CSRF-Token':session.csrf};
 const made=await(await page.request.post('/api/recurrence/preview',{headers,data:{title:'Combined fixture',day:shiftDay(dayKey(new Date(),'Asia/Jerusalem'),1),clock:'09:00',duration:60,count:3,timezone:'Asia/Jerusalem'}})).json();
 expect((await page.request.post('/api/recurrence/confirm',{headers,data:{id:made.id}})).ok()).toBe(true);
 const rows=await(await page.request.get('/api/events')).json();expect((await page.request.put(`/api/events/${rows[1].id}`,{headers,data:{...rows[1],notes:'Protected combined browser fixture'}})).ok()).toBe(true);
 const before=await(await page.request.get('/api/events')).json();await page.reload();await page.getByRole('button',{name:'ניהול סדרות שבועיות',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'ניהול סדרות שבועיות',exact:true});
 await dialog.getByLabel('פעולה בסדרה',{exact:true}).selectOption('combined');await dialog.getByLabel('מספר ימים להזזה',{exact:true}).fill('2');await dialog.getByLabel('שעה חדשה למופעים',{exact:true}).fill('13:00');await dialog.getByLabel('משך חדש בדקות',{exact:true}).fill('45');
 await dialog.getByRole('button',{name:'תצוגה מקדימה לתאריך ושעה',exact:true}).click();await expect(dialog.locator('.recurring-preview-list li')).toHaveCount(2);expect(await(await page.request.get('/api/events')).json()).toEqual(before);
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await dialog.getByRole('button',{name:'אישור תאריך ושעה של 2 מופעים',exact:true}).click();await expect(dialog.getByText('עודכנו התאריכים והשעות של 2 מופעים שנבדקו.',{exact:true})).toBeVisible();
 const after=await(await page.request.get('/api/events')).json();
 for(const old of before){const row=after.find((value:{id:string})=>value.id===old.id);if(old.id===rows[1].id)expect(row).toEqual(old);else{expect(dayKey(new Date(row.start),'Asia/Jerusalem')).toBe(shiftDay(dayKey(new Date(old.start),'Asia/Jerusalem'),2));expect(Date.parse(row.end)-Date.parse(row.start)).toBe(45*60000);expect(new Intl.DateTimeFormat('en',{timeZone:'Asia/Jerusalem',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(row.start))).toBe('13:00');}}
 await dialog.getByRole('button',{name:'סגירה',exact:true}).click();expect((await page.request.put('/api/settings',{headers,data:{language:'en',theme:'light',timezone:'Asia/Jerusalem'}})).ok()).toBe(true);await page.reload();await page.getByRole('button',{name:'Manage weekly series',exact:true}).click();await page.getByLabel('Series action',{exact:true}).selectOption('combined');await expect(page.getByRole('button',{name:'Preview date and time changes',exact:true})).toBeVisible();
});
