import { test, expect } from '@playwright/test';

for (const failedRead of [1, 2]) {
  test(`account refresh reports a failed identity read ${failedRead} and retains a draft`, async ({ browser }) => {
    test.skip(process.env.LIFEOS_TRANSITION_E2E !== '1', 'Requires isolated migrated .runtime fixture');
    const base = process.env.LIFEOS_TEST_BASE_URL;
    if (!base || new URL(base).hostname !== '127.0.0.1' || new URL(base).port === '3000') throw Error('Isolated fixture server required');
    const context = await browser.newContext({ baseURL: base });
    try {
      expect(await (await context.request.get('/api/mode')).json()).toMatchObject({account_mode:true,test_mode:true});
      await context.addCookies([{name:'lifeos_session',value:'transition-fixture-token',domain:'127.0.0.1',path:'/',httpOnly:true,sameSite:'Strict'}]);
      const page=await context.newPage();
      await page.goto('/?view=tasks');
      await expect(page.locator('#page-title')).toBeVisible();
      await expect(page.getByText('Private title',{exact:true})).toBeVisible();
      await page.getByRole('button',{name:'משימה חדשה',exact:true}).click();
      const draft=page.getByRole('dialog').getByLabel('כותרת',{exact:true});
      await draft.fill('טיוטת דמה שנשמרת בניתוק');
      let reads=0;
      await page.route('**/api/session',async route=>{
        reads++;
        if(reads===failedRead) await route.fulfill({status:503,json:{detail:'Fixture identity unavailable'}});
        else await route.continue();
      });
      await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
      const warning=page.getByText('התצוגה אינה מעודכנת. יש לרענן לפני פעולה נוספת.',{exact:true});
      await expect(warning).toBeVisible();
      await expect(draft).toHaveValue('טיוטת דמה שנשמרת בניתוק');
      await page.unroute('**/api/session');
      await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
      await expect(warning).toHaveCount(0);
      await expect(draft).toHaveValue('טיוטת דמה שנשמרת בניתוק');
      await page.keyboard.press('Escape');
      await expect(draft).toHaveValue('טיוטת דמה שנשמרת בניתוק');
      page.once('dialog', async confirmation => {
        expect(confirmation.type()).toBe('confirm');
        expect(confirmation.message()).toBe('לסגור בלי לשמור את השינויים?');
        await confirmation.accept();
      });
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await expect(page.getByText('Private title',{exact:true})).toBeVisible();
    } finally { await context.close(); }
  });
}


test('a delayed final account identity read cannot replace a newer snapshot', async ({ browser }) => {
  test.skip(process.env.LIFEOS_TRANSITION_E2E !== '1', 'Requires isolated migrated .runtime fixture');
  const base=process.env.LIFEOS_TEST_BASE_URL;
  if(!base||new URL(base).hostname!=='127.0.0.1'||new URL(base).port==='3000')throw Error('Isolated fixture server required');
  const context=await browser.newContext({baseURL:base});
  let release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve;});
  try{
    expect(await(await context.request.get('/api/mode')).json()).toMatchObject({account_mode:true,test_mode:true});
    await context.addCookies([{name:'lifeos_session',value:'transition-fixture-token',domain:'127.0.0.1',path:'/',httpOnly:true,sameSite:'Strict'}]);
    const page=await context.newPage();await page.goto('/?view=tasks');await expect(page.getByText('Private title',{exact:true})).toBeVisible();
    const session=await(await context.request.get('/api/session')).json();
    let reads=0,captured!:()=>void;
    const oldFinalRead=new Promise<void>(resolve=>{captured=resolve;});
    await page.route('**/api/session',async route=>{reads++;if(reads===2){const response=await route.fetch();captured();await gate;await route.fulfill({response});}else await route.continue();});
    await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await oldFinalRead;
    const title='Newer account snapshot fixture '+Date.now();
    expect((await context.request.post('/api/tasks',{headers:{Origin:base,'X-CSRF-Token':session.csrf},data:{title}})).ok()).toBe(true);
    await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect(page.getByText(title,{exact:true})).toBeVisible();
    release();await page.unrouteAll({behavior:'wait'});
    await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
    await expect(page.getByText(title,{exact:true})).toBeVisible();
  }finally{release();await context.close();}
});
