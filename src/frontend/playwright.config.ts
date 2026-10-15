import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';
export default defineConfig({testDir:'./tests',timeout:20000,fullyParallel:false,workers:1,retries:0,
 reporter:[['./tests/safe-reporter.ts']],outputDir:'.runtime/test-results',
 use:{baseURL:'http://127.0.0.1:5173',browserName:'chromium',trace:'off',video:'off',screenshot:'off'},
 webServer:{env:{PORTAL_TEST_PORTS:'1'},command:`"${resolve('../backend/.venv/bin/python')}" -m scripts.portal_test_server`,cwd:resolve('../backend'),
 url:'http://127.0.0.1:5173/api/v1/health',timeout:20000,reuseExistingServer:false,stdout:'ignore',stderr:'ignore',
 gracefulShutdown:{signal:'SIGTERM',timeout:5000}}});
