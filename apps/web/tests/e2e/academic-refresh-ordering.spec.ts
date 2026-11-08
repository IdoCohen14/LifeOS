import { test, expect } from "@playwright/test";
import { prepareFixtures } from "./helpers";
test.beforeEach(async ({ playwright }) => prepareFixtures(playwright));
test("an obsolete academic session error cannot reopen login after leaving the view", async ({page})=>{
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button",{name:"כניסה למרחב שלך"}).click();
  await expect(page.locator("#page-title")).toBeVisible();
  expect((await (await page.request.get("/api/session")).json()).test_mode).toBe(true);
  let release!:()=>void,seen!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve;});
  const started=new Promise<void>(resolve=>{seen=resolve;});
  let count=0;
  await page.route("**/api/academic/courses",async route=>{
    if(count++===0){seen();await gate;await route.fulfill({status:401,json:{detail:"Fixture obsolete session"}});}
    else await route.continue();
  });
  await page.getByRole("link",{name:"המרחב האקדמי",exact:true}).click();
  await started;
  await page.getByRole("link",{name:"היום שלי",exact:true}).click();
  await page.getByRole("link",{name:"המרחב האקדמי",exact:true}).click();
  await expect(page.getByRole("heading",{name:"הקורסים שלי",exact:true})).toBeVisible();
  const obsolete=page.waitForResponse(response=>response.url().endsWith("/api/academic/courses")&&response.status()===401);
  release();await obsolete;
  await page.unrouteAll({behavior:"wait"});
  await expect(page.getByLabel("הסיסמה שלך")).toHaveCount(0);
  await expect(page.getByRole("heading",{name:"הקורסים שלי",exact:true})).toBeVisible();
  await expect(page.locator(".academic-workspace [role=alert]")).toHaveCount(0);
});
