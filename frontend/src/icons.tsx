import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement> & {size?:number;fill?:string};
function icon(path:string, secondary?:string){return function Icon({size=24,...props}:IconProps){return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={path}/>{secondary&&<path d={secondary}/>}</svg>}}

export const Activity=icon('M3 12h4l3-8 4 16 3-8h4');
export const AlertTriangle=icon('M10.3 3.9 2.7 17a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z','M12 9v4m0 4h.01');
export const ArrowDownToLine=icon('M12 3v12m-5-5 5 5 5-5M5 21h14');
export const Bell=icon('M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12h4');
export const Blocks=icon('M3 3h8v8H3zm10 0h8v8h-8zM3 13h8v8H3zm10 0h8v8h-8z');
export const ChartNoAxesCombined=icon('M3 3v18h18M7 14l4-4 4 4 6-7m-5 0h5v5');
export const ChevronLeft=icon('m15 18-6-6 6-6');
export const ChevronRight=icon('m9 18 6-6-6-6');
export const CircleHelp=icon('M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3m.1 4h.01','M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z');
export const ExternalLink=icon('M14 3h7v7m0-7-9 9','M19 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h6');
export const Gauge=icon('M20 13a8 8 0 1 0-16 0m8 0 4-5m-4 5v.01M4 17h16');
export const LayoutDashboard=icon('M3 3h8v8H3zm10 0h8v5h-8zm0 7h8v11h-8zM3 13h8v8H3z');
export const ListFilter=icon('M4 6h16M7 12h10m-7 6h4');
export const Play=icon('m7 4 13 8-13 8z');
export const RefreshCw=icon('M20 7v5h-5M4 17v-5h5m-4-2a8 8 0 0 1 13-4l2 1m-16 10-2 1a8 8 0 0 0 13-4');
export const Search=icon('M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm6-2 4 4');
export const ShieldAlert=icon('M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z','M12 8v4m0 4h.01');
export const Siren=icon('M5 18h14l-1.5-9a5.6 5.6 0 0 0-11 0L5 18Zm-2 3h18M12 2v2M3 8l2 1m16-1-2 1');
export const Square=icon('M5 5h14v14H5z');
export const Workflow=icon('M4 4h6v6H4zm10 10h6v6h-6zM10 7h4a4 4 0 0 1 4 4v3');
