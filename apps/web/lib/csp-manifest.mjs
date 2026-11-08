import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, readdirSync, existsSync, lstatSync } from 'node:fs';
import { join, resolve } from 'node:path';

const manifestName='lifeos-csp.json';
const digest=value=>createHash('sha256').update(value).digest('base64');

export function buildDirectory(name=process.env.LIFEOS_BUILD_DIR || '.next') {
  if(!/^\.next(?:-[a-z0-9-]+)?$/.test(name))throw Error('Invalid build directory');
  // Build artifacts are supplied by our build/release workflow, not server tracing.
  return resolve(/* turbopackIgnore: true */ process.cwd(),name);
}

function inventory(directory){
  const buildId=readFileSync(join(directory,'BUILD_ID'),'utf8').trim();
  if(!buildId || buildId.length>200)throw Error('Invalid build identity');
  const files=[],hashes=new Set();let bytes=0;
  function visit(folder){
    for(const entry of readdirSync(folder,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){
      const path=join(folder,entry.name);
      if(entry.isSymbolicLink())throw Error('Linked build content is not supported');
      if(entry.isDirectory())visit(path);
      else if(entry.name.endsWith('.html')){
        const content=readFileSync(path);bytes+=content.length;
        if(files.length>=128||bytes>32*1024*1024)throw Error('CSP inventory limit');
        const text=content.toString('utf8');
        for(const match of text.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)){
          if(!/(?:^|\s)src\s*=/.test(match[1]) && match[2])hashes.add(`'sha256-${digest(match[2])}'`);
        }
        files.push({path:path.slice(directory.length+1).replaceAll('\\','/'),digest:digest(content)});
      }
    }
  }
  for(const name of ['app','pages']){const folder=join(directory,'server',name);if(existsSync(folder))visit(folder)}
  if(!files.length||!hashes.size)throw Error('Missing static HTML or inline script inventory');
  return {version:1,buildId,files,hashes:[...hashes].sort()};
}

export function createManifest(directory){
  const value=inventory(directory);
  writeFileSync(join(directory,manifestName),JSON.stringify(value,null,2));
  return value;
}

export function verifyManifest(directory){
  const path=join(directory,manifestName);
  if(lstatSync(path).isSymbolicLink())throw Error('Linked CSP manifest is not supported');
  const value=JSON.parse(readFileSync(path,'utf8'));
  if(JSON.stringify(value)!==JSON.stringify(inventory(directory)))throw Error('CSP manifest does not match the selected build');
  return value;
}

export function verifyBuild(directory){
  const config=JSON.parse(readFileSync(join(directory,'required-server-files.json'),'utf8'));
  const version=config.config?.env?.LIFEOS_CSP_BUILD_VERSION;
  if(version===undefined)return {mode:'legacy'};
  if(version!=='1')throw Error('Unknown CSP build version');
  return {mode:'hash',manifest:verifyManifest(directory)};
}

export function scriptPolicy(hashes){
  const value=`default-src 'self'; script-src 'self' ${hashes.join(' ')}; script-src-attr 'none'; object-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`;
  if(value.length>16000)throw Error('CSP header limit');
  return value;
}
