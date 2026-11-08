import {test,expect} from '@playwright/test';
import {prepareFixtures} from './helpers';
test.beforeEach(async({playwright})=>prepareFixtures(playwright));
test('academic resource failures show explicit incomplete-load feedback and retry',async({page})=>{
 await page.goto('/');await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');await page.getByRole('button',{name:'כניסה למרחב שלך'}).click();await expect(page.locator('#page-title')).toBeVisible();expect((await(await page.request.get('/api/session')).json()).test_mode).toBe(true);
 let limited=true;
 await page.route('**/api/academic/courses',route=>limited?route.fulfill({status:503,json:{detail:'academic_resource_limit'}}):route.continue());
 await page.getByRole('link',{name:'המרחב האקדמי',exact:true}).click();
 await expect(page.locator('.academic-workspace [role=alert]')).toContainText('לא נטענה רשימה מלאה');
 limited=false;await page.getByRole('button',{name:'ניסיון נוסף',exact:true}).click();await expect(page.locator('.academic-workspace [role=alert]')).toHaveCount(0);await expect(page.getByRole('heading',{name:'הקורסים שלי',exact:true})).toBeVisible();
});
