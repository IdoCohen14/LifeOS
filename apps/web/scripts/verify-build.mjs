import { buildDirectory, verifyBuild } from '../lib/csp-manifest.mjs';
const result=verifyBuild(buildDirectory());
console.log(`CSP preflight: ${result.mode}`);
