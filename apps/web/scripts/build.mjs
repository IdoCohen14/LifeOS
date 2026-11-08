import { spawnSync } from 'node:child_process';
import { buildDirectory, createManifest, verifyBuild } from '../lib/csp-manifest.mjs';

const result=spawnSync(process.execPath,['node_modules/next/dist/bin/next','build',...process.argv.slice(2)],{stdio:'inherit',env:process.env});
if(result.error)throw result.error;
if(result.status!==0)process.exit(result.status || 1);
const directory=buildDirectory();
const manifest=createManifest(directory);
verifyBuild(directory);
console.log(`CSP: verified ${manifest.files.length} HTML artifacts, ${manifest.hashes.length} script hashes.`);
