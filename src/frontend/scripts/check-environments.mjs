import {loadEnvironment,environments} from './environment.mjs';
console.log(JSON.stringify(environments.map(environment=>{const config=loadEnvironment(environment,false);return {environment,configured:config.configured};})));
