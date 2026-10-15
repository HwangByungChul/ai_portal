export interface PortalConfiguration {version:number;environment:'local'|'dev'|'tb'|'prd';configured:boolean;bind_host:string;session_mode:string;user:{origin:string|null;port:number;entry:string};admin:{origin:string|null;port:number;entry:string};api:{origin:string|null;port:number;entry:string}}
export const environments:string[];
export function loadEnvironment(environment?:string,ready?:boolean):PortalConfiguration;
export function validateEnvironment(data:unknown,expected:string,ready?:boolean):PortalConfiguration;
