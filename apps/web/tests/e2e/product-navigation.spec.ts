import {test,expect} from '@playwright/test';
import {prepareFixtures} from './helpers';
test.beforeEach(async({playwright})=>prepareFixtures(playwright));
test('personal tools navigate to mail and open the existing operational assistant',async({page})=>{
 await page.route('**/api/assistant/status',route=>route.fulfill({json:{ready:false,local:true,state:'runtime_unavailable',model:'fixture'}}));
 await page.goto('/?view=academic');await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');await page.getByRole('button',{name:'כניסה למרחב שלך'}).click();await expect(page.locator('#page-title')).toBeVisible();expect((await(await page.request.get('/api/session')).json()).test_mode).toBe(true);
 await page.getByRole('link',{name:'פתיחת המיילים שלי',exact:true}).click();await expect(page).toHaveURL(/#my-mail$/);await expect(page.locator('#my-mail')).toBeInViewport();await page.getByRole('button',{name:'פתיחת העוזר',exact:true}).click();await expect(page.getByRole('dialog',{name:'העוזר האישי',exact:true})).toBeVisible();await page.getByText('עזרה מובנית באפליקציה',{exact:true}).click();await page.getByLabel('נושא לעזרה',{exact:true}).selectOption('academic_timetable');await expect(page.locator('.help-answer')).toContainText('הוספת מפגשים שבועיים');
});
