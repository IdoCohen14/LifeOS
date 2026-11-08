import { test, expect } from '@playwright/test';
import { BASE, prepareFixtures } from './helpers';

test.beforeEach(async({playwright})=>prepareFixtures(playwright));

test('title-only edits preserve explicit DST offsets and seconds through storage',async({page})=>{
  await page.goto('/?view=tasks');
  await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');
  await page.getByRole('button',{name:'כניסה למרחב שלך'}).click();
  await expect(page.locator('#page-title')).toBeVisible();
  const session=await(await page.request.get('/api/session')).json();expect(session.test_mode).toBe(true);
  const headers={Origin:BASE,'X-CSRF-Token':session.csrf};
  for(const [index,due] of ['2026-10-25T01:30:21+03:00','2026-10-25T01:30:21+02:00'].entries()){
    const title='Exact task fixture '+index;
    const created=await page.request.post('/api/tasks',{headers,data:{title,due,priority:'high',notes:'Fixture note'}});expect(created.ok()).toBe(true);
    const original=await created.json();expect(Date.parse(original.due)).toBe(Date.parse(due));
    await page.reload();await page.getByLabel('אפשרויות: '+title,{exact:true}).click();
    await page.getByRole('button',{name:'עריכה: '+title,exact:true}).click();
    const dialog=page.getByRole('dialog');await dialog.getByLabel('כותרת',{exact:true}).fill(title+' renamed');
    await dialog.getByRole('button',{name:'שמירה',exact:true}).click();await expect(dialog).toHaveCount(0);
    const saved=(await(await page.request.get('/api/tasks')).json()).find((task:{id:string})=>task.id===original.id);
    expect(Date.parse(saved.due)).toBe(Date.parse(due));expect(saved.due).toBe(original.due);expect(saved.notes).toBe('Fixture note');expect(saved.priority).toBe('high');
  }
  for(const item of [
    {title:'Fold crossing fixture',day:'2026-10-25',start:'2026-10-25T01:45:13+03:00',end:'2026-10-25T01:15:41+02:00'},
    {title:'Microsecond fixture',day:'2026-11-12',start:'2026-11-12T15:00:13.000001Z',end:'2026-11-12T15:00:13.000002Z'},
  ]){
    const created=await page.request.post('/api/events',{headers,data:{title:item.title,start:item.start,end:item.end,all_day:false,notes:'Event fixture'}});expect(created.ok()).toBe(true);const original=await created.json();
    await page.goto('/?view=calendar&day='+item.day);await page.getByRole('button',{name:'יום',exact:true}).click();
    await page.getByRole('button',{name:'עריכה: '+item.title,exact:true}).click();
    const dialog=page.getByRole('dialog');await dialog.getByLabel('כותרת',{exact:true}).fill(item.title+' renamed');
    if(item.title==='Fold crossing fixture'){
      const settings=await(await page.request.get('/api/settings')).json();
      expect((await page.request.put('/api/settings',{headers,data:{...settings,timezone:'America/New_York'}})).ok()).toBe(true);
      await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
      await expect(page.locator('.workspace-footer bdi')).toHaveText('America/New_York');
      await expect(dialog.getByText('Asia/Jerusalem',{exact:true})).toBeVisible();
    }

    await dialog.getByRole('button',{name:'שמירה',exact:true}).click();await expect(dialog).toHaveCount(0);
    const saved=(await(await page.request.get('/api/events')).json()).find((event:{id:string})=>event.id===original.id);
    expect(saved.start).toBe(original.start);expect(saved.end).toBe(original.end);
  }
});


test('academic title edits preserve the exact linked-task deadline',async({page})=>{
  await page.goto('/?view=academic');await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');await page.getByRole('button',{name:'כניסה למרחב שלך'}).click();await expect(page.locator('#page-title')).toBeVisible();
  const session=await(await page.request.get('/api/session')).json();expect(session.test_mode).toBe(true);const headers={Origin:BASE,'X-CSRF-Token':session.csrf};
  async function create(kind:string,data:object){const response=await page.request.post('/api/academic/'+kind,{headers,data});expect(response.ok()).toBe(true);return response.json();}
  const term=await create('terms',{name:'Exact term fixture',start_date:'2026-10-01',end_date:'2027-02-01'});
  const course=await create('courses',{name:'Exact course fixture',term_id:term.id});
  for(const [index,due] of ['2026-10-25T01:30:21+02:00','2026-11-12T15:00:37Z','2026-10-25'].entries()){
    const title='Exact academic fixture '+index;
    const item=await create('items',{course_id:course.id,title,kind:'assignment',due,notes:'Fixture note'});
    await page.goto('/?view=academic&course='+course.id);
    const row=page.locator('.course-panel .academic-list li').filter({has:page.getByText(title,{exact:true})});
    await row.locator('.item-extra>summary').click();await row.getByRole('button',{name:'עריכה: '+title,exact:true}).click();
    const dialog=page.getByRole('dialog');await dialog.getByLabel('כותרת',{exact:true}).fill(title+' renamed');
    await dialog.getByRole('button',{name:'שמירה',exact:true}).click();await expect(dialog).toHaveCount(0);
    const saved=(await(await page.request.get('/api/academic/items')).json()).find((record:{id:string})=>record.id===item.id);
    const linked=(await(await page.request.get('/api/tasks')).json()).find((task:{id:string})=>task.id===item.task_id);
    expect(saved.due).toBe(item.due);expect(linked.due).toBe(item.due);expect(saved.notes).toBe('Fixture note');
  }
});
