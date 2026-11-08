import { defineConfig, devices } from "@playwright/test";
export default defineConfig({testDir:"./tests/recovery-e2e",workers:1,retries:0,timeout:30000,use:{baseURL:"http://127.0.0.1:8877",...devices["Desktop Chrome"],channel:"chrome",trace:"retain-on-failure"},reporter:"list"});
