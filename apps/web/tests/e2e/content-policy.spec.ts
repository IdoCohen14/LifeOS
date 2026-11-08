import {test,expect} from '@playwright/test';

test('production content policy blocks an external connection before any network request',async({page})=>{
 const response=await page.goto('/');expect(response?.ok()).toBe(true);
 const policy=response?.headers()['content-security-policy']??'';
 expect(policy).toContain("connect-src 'self'");expect(policy).not.toContain("'unsafe-eval'");
 let externalRequests=0;
 await page.route('https://lifeos-csp-fixture.invalid/**',route=>{externalRequests++;return route.abort();});
 const result=await page.evaluate(async()=>{
   const violations:string[]=[];
   const listener=(event:SecurityPolicyViolationEvent)=>violations.push(event.effectiveDirective);
   document.addEventListener('securitypolicyviolation',listener);
   let rejected=false;
   try{await fetch('https://lifeos-csp-fixture.invalid/test');}catch{rejected=true;}
   const script=document.createElement('script');
   script.src='https://lifeos-csp-fixture.invalid/script.js';
   await new Promise<void>(resolve=>{script.onerror=()=>resolve();script.onload=()=>resolve();document.head.appendChild(script);});
   script.remove();
   await new Promise(resolve=>setTimeout(resolve,100));
   document.removeEventListener('securitypolicyviolation',listener);
   return {rejected,violations};
 });
 expect(result.rejected).toBe(true);expect(result.violations).toContain('connect-src');expect(result.violations).toContain('script-src-elem');expect(externalRequests).toBe(0);
});
