import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement> & { size?: number; fill?: string };

function icon(path: string, secondary?: string) {
  return function Icon({ size = 18, ...props }: IconProps) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        {...props}
      >
        <path d={path} />
        {secondary && <path d={secondary} />}
      </svg>
    );
  };
}

export const Activity = icon('M3 12h4l3-8 4 16 3-8h4');
export const AlertTriangle = icon('M10.3 3.9 2.7 17a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z', 'M12 9v4m0 4h.01');
export const ArrowDownToLine = icon('M12 3v12m-5-5 5 5 5-5M5 21h14');
export const Bell = icon('M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12h4');
export const Blocks = icon('M3 3h8v8H3zm10 0h8v8h-8zM3 13h8v8H3zm10 0h8v8h-8z');
export const ChartNoAxesCombined = icon('M3 3v18h18M7 14l4-4 4 4 6-7m-5 0h5v5');
export const ChevronLeft = icon('m15 18-6-6 6-6');
export const ChevronRight = icon('m9 18 6-6-6-6');
export const ChevronDown = icon('m6 9 6 6 6-6');
export const ChevronUp = icon('m18 15-6-6-6 6');
export const CircleHelp = icon('M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3m.1 4h.01', 'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z');
export const HelpCircle = CircleHelp;
export const ExternalLink = icon('M14 3h7v7m0-7-9 9', 'M19 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h6');
export const Gauge = icon('M20 13a8 8 0 1 0-16 0m8 0 4-5m-4 5v.01M4 17h16');
export const LayoutDashboard = icon('M3 3h8v8H3zm10 0h8v5h-8zm0 7h8v11h-8zM3 13h8v8H3z');
export const ListFilter = icon('M4 6h16M7 12h10m-7 6h4');
export const Filter = ListFilter;
export const Play = icon('m7 4 13 8-13 8z');
export const RefreshCw = icon('M20 7v5h-5M4 17v-5h5m-4-2a8 8 0 0 1 13-4l2 1m-16 10-2 1a8 8 0 0 0 13-4');
export const Search = icon('M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm6-2 4 4');
export const ShieldAlert = icon('M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z', 'M12 8v4m0 4h.01');
export const Siren = icon('M5 18h14l-1.5-9a5.6 5.6 0 0 0-11 0L5 18Zm-2 3h18M12 2v2M3 8l2 1m16-1-2 1');
export const Square = icon('M5 5h14v14H5z');
export const Workflow = icon('M4 4h6v6H4zm10 10h6v6h-6zM10 7h4a4 4 0 0 1 4 4v3');

export const CheckCircle = icon('M22 11.08V12a10 10 0 1 1-5.93-9.14', 'm9 11 3 3L22 4');
export const XCircle = icon('M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z', 'm15 9-6 6m0-6 6 6');
export const Copy = icon('M8 8V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-4', 'M4 8h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2Z');
export const Database = icon('M3 5c0-1.66 4-3 9-3s9 1.34 9 3v14c0 1.66-4 3-9 3s-9-1.34-9-3V5Z', 'M3 12c0 1.66 4 3 9 3s9-1.34 9-3');
export const Cpu = icon('M4 4h16v16H4V4Z', 'M9 9h6v6H9V9zM9 1v3m6-3v3M9 20v3m6-3v3M1 9h3m-3 6h3M20 9h3m-3 6h3');
export const Server = icon('M2 4h20v6H2V4zm0 10h20v6H2v-6z', 'M6 7h.01M6 17h.01');
export const Sparkles = icon('m12 3 1.9 4.8L19 9.7l-4 3.4 1.2 5-4.2-2.6-4.2 2.6 1.2-5-4-3.4 5.1-1.9z');
export const Sliders = icon('M4 21v-7m0-4V3m8 18v-9m0-4V3m8 18v-5m0-4V3M1 14h6m2-6h6m2 8h6');
export const FileText = icon('M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', 'M14 2v6h6M16 13H8m8 4H8m2-8H8');
export const ArrowUpDown = icon('m21 16-4 4-4-4m4 4V4M3 8l4-4 4 4M7 4v16');
export const Clock = icon('M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z', 'M12 6v6l4 2');
export const Eye = icon('M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z', 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z');
export const Plus = icon('M5 12h14m-7-7v14');
export const Check = icon('M20 6 9 17l-5-5');
export const X = icon('M18 6 6 18M6 6l12 12');
export const Layers = icon('m12 2 10 5-10 5-10-5 10-5zm-10 9 10 5 10-5m-20 4 10 5 10-5');
export const TrendingUp = icon('m22 7-8.5 8.5-5-5L2 17', 'M16 7h6v6');
