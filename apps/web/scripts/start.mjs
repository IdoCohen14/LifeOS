import { spawnSync } from 'node:child_process';
import { buildDirectory, verifyBuild } from '../lib/csp-manifest.mjs';

const result=verifyBuild(buildDirectory());
console.log(`CSP preflight: ${result.mode}${result.mode==='legacy'?' (previous build, unchanged policy)':''}`);
const child=spawnSync(process.execPath,['node_modules/next/dist/bin/next','start',...process.argv.slice(2)],{stdio:'inherit',env:process.env});
if(child.error)throw child.error;
process.exit(child.status ?? 1);
