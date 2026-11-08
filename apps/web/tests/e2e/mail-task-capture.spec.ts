import {test,expect} from '@playwright/test';
import {prepareFixtures} from './helpers';

test.beforeEach(async({playwright})=>prepareFixtures(playwright));
test('mail task draft saves its source only after approval and leaves the queue alone',async({page})=>{
 const message={id:'mail-task-fixture',subject:'Course action fixture',sender:'Teacher fixture',snippet:'Private body fixture',source_url:'https://mail.google.com/mail/u/0/#inbox/mail-task-fixture',cached_thread_count:2};
 let reviews=0;
 await page.route('**/api/integrations/gmail/status',route=>route.fulfill({json:{connected:true,last_success:1,stale:false}}));
 await page.route('**/api/integrations/gmail/queue',route=>route.fulfill({json:[message]}));
 await page.route('**/api/integrations/gmail/review',route=>{reviews++;return route.fulfill({json:[]});});
 await page.goto('/');await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');await page.getByRole('button',{name:'כניסה למרחב שלך'}).click();
 await expect(page.locator('#page-title')).toBeVisible();
 expect((await(await page.request.get('/api/session')).json()).test_mode).toBe(true);
 const before=await(await page.request.get('/api/tasks')).json();
 await expect(page.locator('#my-mail')).toContainText('בשיחה הזו 2 הודעות רלוונטיות');
 await page.getByRole('button',{name:'יצירת משימה מהמייל',exact:true}).click();
 const dialog=page.getByRole('dialog');await expect(dialog.getByLabel('כותרת',{exact:true})).toHaveValue(message.subject);
 expect(await(await page.request.get('/api/tasks')).json()).toEqual(before);
 await dialog.getByRole('button',{name:'ביטול',exact:true}).click();
 await expect(dialog).toBeHidden();expect(await(await page.request.get('/api/tasks')).json()).toEqual(before);expect(reviews).toBe(0);
 await page.getByRole('button',{name:'יצירת משימה מהמייל',exact:true}).click();
 await dialog.getByLabel('כותרת',{exact:true}).fill('Review timetable fixture');
 await dialog.getByRole('button',{name:'שמירה',exact:true}).click();
 await expect(dialog).toBeHidden();
 const tasks=await(await page.request.get('/api/tasks')).json();const created=tasks.find((task:{title:string})=>task.title==='Review timetable fixture');
 expect(created).toBeTruthy();expect(created.notes).toContain(message.source_url);expect(created.notes).toContain(message.sender);expect(created.notes).not.toContain(message.snippet);expect(created.due).toBeNull();
 await expect(page.locator('#my-mail')).toContainText(message.subject);expect(reviews).toBe(0);
});
