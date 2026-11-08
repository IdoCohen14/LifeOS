import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { createManifest, verifyManifest, verifyBuild } from '../lib/csp-manifest.mjs';

const fixtureRoot=resolve('../../.runtime/csp-manifest-tests');
mkdirSync(fixtureRoot,{recursive:true});
function fixture(run){const dir=mkdtempSync(join(fixtureRoot,'build-'));try{
 mkdirSync(join(dir,'server/app'),{recursive:true});writeFileSync(join(dir,'BUILD_ID'),'fixture-build');
 writeFileSync(join(dir,'required-server-files.json'),JSON.stringify({config:{env:{LIFEOS_CSP_BUILD_VERSION:'1'}}}));
 writeFileSync(join(dir,'server/app/index.html'),'<script src="/bundle.js"></script><script>window.fixture=1;</script>');
 run(dir);
}finally{rmSync(dir,{recursive:true,force:true})}}
test('manifest permits only the built inline contents and matches its build',()=>fixture(dir=>{
 const value=createManifest(dir);assert.equal(value.hashes.length,1);assert.equal(verifyManifest(dir).buildId,'fixture-build');assert.equal(verifyBuild(dir).mode,'hash');
}));
test('missing manifest and an altered build are refused',()=>fixture(dir=>{
 assert.throws(()=>verifyBuild(dir));createManifest(dir);writeFileSync(join(dir,'BUILD_ID'),'another-build');assert.throws(()=>verifyManifest(dir));
}));
test('altering HTML after generation is refused',()=>fixture(dir=>{
 createManifest(dir);writeFileSync(join(dir,'server/app/index.html'),'<script>window.fixture=2;</script>');assert.throws(()=>verifyManifest(dir));
}));
test('legacy output is recognized only when the new marker is absent',()=>fixture(dir=>{
 writeFileSync(join(dir,'required-server-files.json'),JSON.stringify({config:{env:{}}}));assert.equal(verifyBuild(dir).mode,'legacy');
 writeFileSync(join(dir,'required-server-files.json'),JSON.stringify({config:{env:{LIFEOS_CSP_BUILD_VERSION:'2'}}}));assert.throws(()=>verifyBuild(dir));
}));
test('the actual start command refuses a marked build without manifest before Next starts',()=>fixture(dir=>{
 const build=join(dir,'.next');mkdirSync(build);writeFileSync(join(build,'required-server-files.json'),JSON.stringify({config:{env:{LIFEOS_CSP_BUILD_VERSION:'1'}}}));
 const result=spawnSync(process.execPath,[resolve('scripts/start.mjs')],{cwd:dir,encoding:'utf8',env:{...process.env,LIFEOS_BUILD_DIR:'.next'}});
 assert.notEqual(result.status,0);assert.match(result.stderr,/lifeos-csp\.json/);
}));
