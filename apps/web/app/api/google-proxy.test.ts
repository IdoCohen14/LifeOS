// @vitest-environment node
import {createServer} from 'node:http';
import {afterEach,expect,it,vi} from 'vitest';
import {NextRequest} from 'next/server';
import {GET,POST,PATCH} from './[...path]/route';
afterEach(()=>vi.unstubAllEnvs());
it('routes a versioned request patch to the owned API and rejects cross-origin changes',async()=>{
 const seen:string[]=[];const server=createServer((request,response)=>{seen.push(`${request.method} ${request.url}`);response.writeHead(200,{'Content-Type':'application/json'});response.end('{}');});
 await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));const address=server.address();if(!address||typeof address==='string')throw Error('No address');
 vi.stubEnv('LIFEOS_ACCOUNT_MODE','1');vi.stubEnv('LIFEOS_API_KEY','fixture');vi.stubEnv('LIFEOS_API_PORT',String(address.port));vi.stubEnv('LIFEOS_WEB_PORT','3100');
 const id='00000000-0000-0000-0000-000000000001';const path=['assistant','requests',id];
 try{
  const response=await PATCH(new NextRequest(`http://127.0.0.1:3100/api/assistant/requests/${id}`,{method:'PATCH',headers:{host:'127.0.0.1:3100',origin:'http://127.0.0.1:3100'},body:'{"version":1,"status":"done"}'}),{params:Promise.resolve({path})});expect(response.status).toBe(200);
  expect(seen).toEqual([`PATCH /accounts/workspace/assistant/requests/${id}`]);
  const rejected=await PATCH(new NextRequest(`http://127.0.0.1:3100/api/assistant/requests/${id}`,{method:'PATCH',headers:{host:'127.0.0.1:3100',origin:'https://foreign.test'}}),{params:Promise.resolve({path})});expect(rejected.status).toBe(403);expect(seen).toHaveLength(1);
 }finally{await new Promise<void>((resolve,reject)=>server.close(error=>error?reject(error):resolve()));}
});
it('uses configured HTTPS origin and owned paths behind a loopback server',async()=>{
  const seen:string[]=[];
  const server=createServer((request,response)=>{
    seen.push(request.url||'');
    if(request.url?.startsWith('/accounts/oauth/callback')){
      response.writeHead(303,{Location:'/?view=settings&google=connected'});response.end();
    }else{response.writeHead(200,{'Set-Cookie':'lifeos_session=fixture; HttpOnly; Secure; SameSite=Lax'});response.end('{}');}
  });
  await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
  const address=server.address();if(!address||typeof address==='string')throw new Error('No fixture address');
  vi.stubEnv('LIFEOS_DEPLOYMENT_MODE','server');vi.stubEnv('LIFEOS_PUBLIC_ORIGIN','https://lifeos.example');
  vi.stubEnv('LIFEOS_API_KEY','fixture');vi.stubEnv('LIFEOS_API_PORT',String(address.port));
  try{
    const context={params:Promise.resolve({path:['session']})};
    const valid=await POST(new NextRequest('http://127.0.0.1:3000/api/session',{method:'POST',headers:{host:'lifeos.example',origin:'https://lifeos.example'}}),context);
    expect(valid.status).toBe(200);expect(valid.headers.get('set-cookie')).toContain('Secure');
    for(const headers of [{host:'other.example',origin:'https://lifeos.example'},{host:'lifeos.example',origin:'https://other.example'}]){
      expect((await POST(new NextRequest('http://127.0.0.1:3000/api/session',{method:'POST',headers}),context)).status).toBe(403);
    }
    const callback=await GET(new NextRequest('http://127.0.0.1:3000/api/accounts/oauth/callback?code=fixture',{headers:{host:'lifeos.example','Sec-Fetch-Site':'cross-site'}}),{params:Promise.resolve({path:['accounts','oauth','callback']})});
    expect(callback.headers.get('location')).toBe('https://lifeos.example/?view=settings&google=connected');
    expect(seen).toEqual(['/accounts/session','/accounts/oauth/callback?code=fixture']);
  }finally{await new Promise<void>((resolve,reject)=>server.close(error=>error?reject(error):resolve()));}
});
it('preserves the OAuth callback redirect without following it at the API',async()=>{
  let requests=0;
  const server=createServer((request,response)=>{requests++;if(request.url?.startsWith('/integrations/google/callback')){response.writeHead(303,{Location:'/?view=settings&google=connected'});response.end();}else{response.writeHead(404);response.end();}});
  await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
  const address=server.address();if(!address||typeof address==='string')throw new Error('No test address');
  vi.stubEnv('LIFEOS_API_KEY','fixture');vi.stubEnv('LIFEOS_API_PORT',String(address.port));vi.stubEnv('LIFEOS_WEB_PORT','3100');
  try{
    const request=new NextRequest('http://127.0.0.1:3100/api/integrations/google/callback?state=fixture&code=fixture',{headers:{host:'127.0.0.1:3100','Sec-Fetch-Site':'cross-site'}});
    const response=await GET(request,{params:Promise.resolve({path:['integrations','google','callback']})});
    expect(response.status).toBe(303);expect(response.headers.get('location')).toBe('http://127.0.0.1:3100/?view=settings&google=connected');expect(requests).toBe(1);
  }finally{await new Promise<void>((resolve,reject)=>server.close(error=>error?reject(error):resolve()));}
});

it('routes account mode workspace and OAuth return through their isolated paths',async()=>{
  const seen:string[]=[];
  const server=createServer((request,response)=>{seen.push(request.url||'');
    if(request.url?.startsWith('/accounts/oauth/callback')){response.writeHead(303,{Location:'/?view=settings&google=connected'});response.end();}
    else {response.writeHead(200,{'Content-Type':'application/json'});response.end('{}');}});
  await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
  const address=server.address();if(!address||typeof address==='string')throw new Error('No test address');
  vi.stubEnv('LIFEOS_ACCOUNT_MODE','1');vi.stubEnv('LIFEOS_API_KEY','fixture');vi.stubEnv('LIFEOS_API_PORT',String(address.port));vi.stubEnv('LIFEOS_WEB_PORT','3100');
  try{
    for(const path of ['tasks','session','mode']){
      const response=await GET(new NextRequest('http://127.0.0.1:3100/api/'+path,{headers:{host:'127.0.0.1:3100'}}),{params:Promise.resolve({path:[path]})});
      expect(response.status).toBe(200);
    }
    const path=['accounts','oauth','callback'];
    const callback=await GET(new NextRequest('http://127.0.0.1:3100/api/accounts/oauth/callback?state=fixture&code=fixture',{headers:{host:'127.0.0.1:3100','Sec-Fetch-Site':'cross-site'}}),{params:Promise.resolve({path})});
    expect(callback.status).toBe(303);
    expect(seen).toEqual(['/accounts/workspace/tasks','/accounts/session','/mode','/accounts/oauth/callback?state=fixture&code=fixture']);
  }finally{await new Promise<void>((resolve,reject)=>server.close(error=>error?reject(error):resolve()));}
});
