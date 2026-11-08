import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { execFileSync } from "node:child_process";
const root=resolve(process.cwd(),"../..");
const token=readFileSync(resolve(root,".runtime/recovery-wizard-token"),"utf8");
const directory=resolve(root,".runtime/recovery-wizard");
function title(){return execFileSync(resolve(root,".venv/Scripts/python.exe"),["-c","import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('select title from tasks').fetchone()[0])",resolve(directory,"lifeos.sqlite3")],{encoding:"utf8"}).trim();}

test("test-mode recovery clearly labels its synthetic data",async({page})=>{
 const state=await(await page.request.get("/api/state",{headers:{"X-Recovery-Token":token}})).json();
 expect(state.test_mode).toBe(true);expect(state.directory).toBe(directory);
 await page.goto(`/#${token}`);
 await expect(page.getByText("מצב בדיקה — נתוני דוגמה בלבד",{exact:true})).toBeVisible();
 await page.getByRole("button",{name:"English",exact:true}).click();
 await expect(page.getByText("Test mode — synthetic data only",{exact:true})).toBeVisible();
});

test("external encrypted fixture file can be picked and reviewed without replacement",async({page})=>{
 const state=await(await page.request.get('/api/state',{headers:{'X-Recovery-Token':token}})).json();expect(state.test_mode).toBe(true);expect(state.directory).toBe(directory);const before=title();const source=state.backups.at(-1);expect(source).toBeTruthy();const bytes=readFileSync(resolve(directory,'backups',source.id+'.lifeosbackup'));
 await page.goto('/#'+token);await expect(page.locator('#source-kind')).toBeEnabled();await page.locator('#source-kind').selectOption('file');await page.getByLabel('קובץ גיבוי מוצפן',{exact:true}).setInputFiles({name:'external-fixture.lifeosbackup',mimeType:'application/octet-stream',buffer:bytes});await page.getByLabel('סיסמת הגיבוי',{exact:true}).fill('wizard fixture backup password');await page.getByRole('button',{name:'בדיקת הגיבוי',exact:true}).click();await expect(page.getByRole('heading',{name:'בדקו לפני שמחליפים'})).toBeVisible();await expect(page.locator('#source-name')).toHaveText('external-fixture.lifeosbackup');await expect(page.getByRole('button',{name:'אישור ושחזור הנתונים',exact:true})).toBeDisabled();expect(title()).toBe(before);
 await page.getByRole('button',{name:'English',exact:true}).click();await expect(page.locator('html')).toHaveAttribute('dir','ltr');await expect(page.locator('#source-name')).toHaveText('external-fixture.lifeosbackup');
});

test("offline wizard checks then explicitly restores only the reviewed synthetic backup",async({page})=>{
 const state=await (await page.request.get("/api/state",{headers:{"X-Recovery-Token":token}})).json();
 expect(state.test_mode,"Refuse any non-fixture wizard").toBe(true);
 expect(state.directory).toBe(directory);
 expect(title()).toBe("Current wizard fixture");
 await page.goto(`/#${token}`);
 await expect(page.locator("#backup")).toBeEnabled();
 expect(page.url()).not.toContain(token);
 await expect(page.locator("#directory")).toHaveText(directory);
 await page.getByLabel("גיבוי שמור",{exact:true}).selectOption(state.backups.at(-1).id);
 await page.getByLabel("סיסמת הגיבוי",{exact:true}).fill("wrong fixture backup password");
 await page.getByRole("button",{name:"בדיקת הגיבוי",exact:true}).click();
 await expect(page.getByRole("alert")).toContainText("לא ניתן לאמת");
 await expect(page.getByLabel("סיסמת הגיבוי",{exact:true})).toHaveValue("");
 expect(title()).toBe("Current wizard fixture");
 await page.getByLabel("סיסמת הגיבוי",{exact:true}).fill("wizard fixture backup password");
 await page.getByRole("button",{name:"בדיקת הגיבוי",exact:true}).click();
 await expect(page.getByRole("heading",{name:"בדקו לפני שמחליפים"})).toBeVisible();
 await expect(page.locator("#tasks")).toHaveText("1");
 await expect(page.getByRole("button",{name:"אישור ושחזור הנתונים",exact:true})).toBeDisabled();
 expect(title()).toBe("Current wizard fixture");
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByLabel("תצוגה",{exact:true}).selectOption("dark");
 await page.screenshot({path:"../../.runtime/screenshots/recovery-wizard-mobile.png",fullPage:true});
 await page.getByRole("button",{name:"English",exact:true}).click();
 await page.getByLabel("Theme",{exact:true}).selectOption("light");
 await expect(page.locator("html")).toHaveAttribute("dir","ltr");
 await page.getByLabel("Enter backup password again to confirm",{exact:true}).fill("wizard fixture backup password");
 await page.getByLabel("I reviewed the backup and target folder, and approve replacing the current data",{exact:true}).check();
 await page.getByRole("button",{name:"Confirm and restore data",exact:true}).click();
 await expect(page.getByRole("heading",{name:"Restore complete",exact:true})).toBeVisible();
 expect(title()).toBe("Saved wizard fixture");
 await expect(page.locator("#restore-password")).toHaveValue("");
 await page.screenshot({path:"../../.runtime/screenshots/recovery-wizard-complete.png",fullPage:true});
});
