/**
 * Set de iconos propio de Finlytics.
 *
 * Por qué no una librería: el registro npm de este proyecto vive detrás de un
 * proxy corporativo y `npm install` no es viable, así que los iconos se dibujan
 * aquí.  Sale a cuenta igualmente — sólo entra en el bundle lo que se usa y no
 * hay una dependencia más que mantener.
 *
 * Convenciones (mantenerlas al añadir iconos nuevos):
 *   · lienzo 24×24, trazo de 2, extremos y uniones redondeados
 *   · sin `fill` (lo hereda `.icon` del CSS) salvo detalles macizos puntuales
 *   · `currentColor`, así que el icono toma el color y se adapta al tema
 *
 * Sustituyen a los emojis, que se renderizaban distinto en cada sistema
 * operativo y no heredaban ni color ni tamaño.
 */
import type { SVGProps, ReactNode, ReactElement } from 'react'

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'children'> {
  /** Lado en px. Por defecto 16, que es el tamaño de la mayoría de la UI. */
  size?: number
  /** Título accesible. Si se omite, el icono se marca como decorativo. */
  title?: string
}

/** Envuelve un trazado en un <svg> con los atributos comunes. */
function make(displayName: string, path: ReactNode) {
  function Icon({ size = 16, title, className, ...rest }: IconProps) {
    return (
      <svg
        viewBox="0 0 24 24"
        width={size}
        height={size}
        className={className ? `icon ${className}` : 'icon'}
        role={title ? 'img' : undefined}
        aria-label={title}
        aria-hidden={title ? undefined : true}
        focusable="false"
        {...rest}
      >
        {title && <title>{title}</title>}
        {path}
      </svg>
    )
  }
  Icon.displayName = displayName
  return Icon
}

/* ── Navegación ─────────────────────────────────────────────────────────── */

export const IconHome = make('IconHome', <>
  <path d="M3 10.2 12 3l9 7.2" />
  <path d="M5.6 12.2V20a1 1 0 0 0 1 1h10.8a1 1 0 0 0 1-1v-7.8" />
</>)

export const IconDashboard = make('IconDashboard', <>
  <rect x="3" y="3" width="7.4" height="8.4" rx="1.4" />
  <rect x="13.6" y="3" width="7.4" height="5.2" rx="1.4" />
  <rect x="3" y="14.6" width="7.4" height="6.4" rx="1.4" />
  <rect x="13.6" y="11.4" width="7.4" height="9.6" rx="1.4" />
</>)

export const IconWallet = make('IconWallet', <>
  <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H18a1 1 0 0 1 1 1v2" />
  <path d="M3 7.5V17a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-2.4" />
  <path d="M20 8.6h-3.6a2.9 2.9 0 0 0 0 5.8H20a1 1 0 0 0 1-1V9.6a1 1 0 0 0-1-1Z" />
</>)

export const IconReceipt = make('IconReceipt', <>
  <path d="M6 2.8h12v18.4l-2.4-1.6-2.4 1.6L12 19.6l-1.2 1.6-2.4-1.6L6 21.2Z" />
  <path d="M9.4 8h5.2M9.4 12h5.2" />
</>)

export const IconChartLine = make('IconChartLine', <>
  <path d="M4 4v14.6a1.4 1.4 0 0 0 1.4 1.4H20" />
  <path d="M7.6 15.4 11 11l2.8 2.6L19 7.4" />
</>)

export const IconChartBar = make('IconChartBar', <>
  <path d="M4 4v14.6a1.4 1.4 0 0 0 1.4 1.4H20" />
  <path d="M8.4 16.6v-4M12.4 16.6V8.4M16.4 16.6v-6.4" />
</>)

export const IconChartPie = make('IconChartPie', <>
  <path d="M20.6 13.4A8.6 8.6 0 1 1 10.6 3.4v9a1 1 0 0 0 1 1Z" />
  <path d="M14.4 3.9a8.6 8.6 0 0 1 5.7 5.7h-5.7Z" />
</>)

export const IconFileText = make('IconFileText', <>
  <path d="M13.4 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.6Z" />
  <path d="M13.4 3v5.6H19" />
  <path d="M8.8 13h6.4M8.8 16.6h4.4" />
</>)

export const IconTrendingUp = make('IconTrendingUp', <>
  <path d="M3.5 16.4 9.2 10.7l3.4 3.4 7.9-7.9" />
  <path d="M15.2 6.2h5.3v5.3" />
</>)

export const IconSettings = make('IconSettings', <>
  <circle cx="12" cy="12" r="3.1" />
  <path d="M19.2 14.6a1.5 1.5 0 0 0 .3 1.65l.06.06a1.8 1.8 0 1 1-2.55 2.55l-.06-.06a1.5 1.5 0 0 0-2.55 1.07v.17a1.8 1.8 0 1 1-3.6 0v-.09a1.5 1.5 0 0 0-2.61-1.01l-.06.06a1.8 1.8 0 1 1-2.55-2.55l.06-.06A1.5 1.5 0 0 0 4.6 13.9h-.17a1.8 1.8 0 1 1 0-3.6h.09A1.5 1.5 0 0 0 5.53 7.7l-.06-.06A1.8 1.8 0 1 1 8.02 5.1l.06.06a1.5 1.5 0 0 0 1.65.3h.08a1.5 1.5 0 0 0 .91-1.37v-.17a1.8 1.8 0 1 1 3.6 0v.09a1.5 1.5 0 0 0 2.55 1.07l.06-.06a1.8 1.8 0 1 1 2.55 2.55l-.06.06a1.5 1.5 0 0 0-.3 1.65v.08a1.5 1.5 0 0 0 1.37.91h.17a1.8 1.8 0 1 1 0 3.6h-.09a1.5 1.5 0 0 0-1.37.91Z" />
</>)

export const IconMenu = make('IconMenu', <path d="M4 6.6h16M4 12h16M4 17.4h16" />)

/* ── Dominio financiero ─────────────────────────────────────────────────── */

export const IconBank = make('IconBank', <>
  <path d="M3.4 9.6 12 4.4l8.6 5.2" />
  <path d="M5.6 10.6v7.6M10 10.6v7.6M14 10.6v7.6M18.4 10.6v7.6" />
  <path d="M3.4 20.4h17.2" />
</>)

export const IconCard = make('IconCard', <>
  <rect x="2.6" y="5" width="18.8" height="14" rx="2.4" />
  <path d="M2.6 9.8h18.8" />
  <path d="M6.4 14.6h3.2" />
</>)

export const IconCoins = make('IconCoins', <>
  <ellipse cx="9" cy="6.6" rx="5.6" ry="2.6" />
  <path d="M3.4 6.6v4.2c0 1.44 2.51 2.6 5.6 2.6" />
  <path d="M3.4 10.8V15c0 1.44 2.51 2.6 5.6 2.6" />
  <ellipse cx="15" cy="14.4" rx="5.6" ry="2.6" />
  <path d="M9.4 14.4v3c0 1.44 2.51 2.6 5.6 2.6s5.6-1.16 5.6-2.6v-3" />
</>)

export const IconBanknote = make('IconBanknote', <>
  <rect x="2.6" y="6" width="18.8" height="12" rx="2.2" />
  <circle cx="12" cy="12" r="2.6" />
  <path d="M6.2 12h.02M17.8 12h.02" />
</>)

export const IconBriefcase = make('IconBriefcase', <>
  <rect x="2.8" y="7.4" width="18.4" height="12.4" rx="2.2" />
  <path d="M8.8 7.4V5.8a1.8 1.8 0 0 1 1.8-1.8h2.8a1.8 1.8 0 0 1 1.8 1.8v1.6" />
  <path d="M2.8 12.6h18.4" />
</>)

export const IconPiggy = make('IconPiggy', <>
  <path d="M3.2 12.4a1.6 1.6 0 0 1 1.6-1.6h.6" />
  <path d="M5.4 10.8A6.4 6.4 0 0 1 11.6 6h1.6a6.4 6.4 0 0 1 6.3 5.2l1.3.9v3.1h-1.9a6.5 6.5 0 0 1-2.1 2.3v2.1h-2.9v-1.3a6.7 6.7 0 0 1-2.6 0v1.3H8.4v-2.1a6.4 6.4 0 0 1-3-5.4Z" />
  <path d="M16.4 11.4h.02" />
</>)

export const IconStore = make('IconStore', <>
  <path d="M3.6 4.6h16.8l1.2 4.2a3.1 3.1 0 0 1-6 1.1 3.1 3.1 0 0 1-6 0 3.1 3.1 0 0 1-6-1.1Z" />
  <path d="M4.6 11.4v7a1.6 1.6 0 0 0 1.6 1.6h11.6a1.6 1.6 0 0 0 1.6-1.6v-7" />
</>)

export const IconBuilding = make('IconBuilding', <>
  <rect x="4.4" y="3" width="15.2" height="18" rx="1.8" />
  <path d="M8.4 7.4h2M13.6 7.4h2M8.4 11.4h2M13.6 11.4h2" />
  <path d="M10 21v-4.2h4V21" />
</>)

/* ── Acciones ───────────────────────────────────────────────────────────── */

export const IconPlus = make('IconPlus', <path d="M12 5.2v13.6M5.2 12h13.6" />)
export const IconClose = make('IconClose', <path d="M6.2 6.2 17.8 17.8M17.8 6.2 6.2 17.8" />)
export const IconCheck = make('IconCheck', <path d="M4.8 12.6 9.6 17.4 19.2 6.8" />)

export const IconTrash = make('IconTrash', <>
  <path d="M3.8 6.4h16.4" />
  <path d="M9 6.4V4.8a1.4 1.4 0 0 1 1.4-1.4h3.2A1.4 1.4 0 0 1 15 4.8v1.6" />
  <path d="M5.8 6.4 6.7 19a1.8 1.8 0 0 0 1.8 1.6h7a1.8 1.8 0 0 0 1.8-1.6l.9-12.6" />
  <path d="M10.4 10.4v6M13.6 10.4v6" />
</>)

export const IconPencil = make('IconPencil', <>
  <path d="M16.2 3.6a2.3 2.3 0 0 1 3.25 3.25L7.6 18.7l-4.2 1 1-4.2Z" />
  <path d="M14.6 5.2 18.8 9.4" />
</>)

export const IconDownload = make('IconDownload', <>
  <path d="M12 3.6v11.2" />
  <path d="M7.6 10.6 12 15l4.4-4.4" />
  <path d="M4.4 17v2.4a1.2 1.2 0 0 0 1.2 1.2h12.8a1.2 1.2 0 0 0 1.2-1.2V17" />
</>)

export const IconUpload = make('IconUpload', <>
  <path d="M12 15.6V4.4" />
  <path d="M7.6 8.8 12 4.4l4.4 4.4" />
  <path d="M4.4 17v2.4a1.2 1.2 0 0 0 1.2 1.2h12.8a1.2 1.2 0 0 0 1.2-1.2V17" />
</>)

export const IconRefresh = make('IconRefresh', <>
  <path d="M20.2 11.4a8.2 8.2 0 0 0-14.3-4.3L3.8 9.2" />
  <path d="M3.8 4.6v4.6h4.6" />
  <path d="M3.8 12.6a8.2 8.2 0 0 0 14.3 4.3l2.1-2.1" />
  <path d="M20.2 19.4v-4.6h-4.6" />
</>)

export const IconSend = make('IconSend', <>
  <path d="M20.8 3.2 10.6 13.4" />
  <path d="M20.8 3.2 14.4 20.8l-3.8-7.4-7.4-3.8Z" />
</>)

export const IconLink = make('IconLink', <>
  <path d="M10.2 13.8a3.6 3.6 0 0 0 5.4.4l3-3a3.6 3.6 0 1 0-5.1-5.1l-1.7 1.7" />
  <path d="M13.8 10.2a3.6 3.6 0 0 0-5.4-.4l-3 3a3.6 3.6 0 1 0 5.1 5.1l1.7-1.7" />
</>)

export const IconLogout = make('IconLogout', <>
  <path d="M9.6 20.4H5.8a1.8 1.8 0 0 1-1.8-1.8V5.4a1.8 1.8 0 0 1 1.8-1.8h3.8" />
  <path d="M15.4 16.4 19.8 12l-4.4-4.4" />
  <path d="M19.8 12H9.2" />
</>)

/* ── Estado y feedback ──────────────────────────────────────────────────── */

export const IconAlert = make('IconAlert', <>
  <path d="M10.5 3.9 2.4 18a1.7 1.7 0 0 0 1.5 2.6h16.2a1.7 1.7 0 0 0 1.5-2.6L13.5 3.9a1.7 1.7 0 0 0-3 0Z" />
  <path d="M12 9.4v4.2M12 17.2h.02" />
</>)

export const IconInfo = make('IconInfo', <>
  <circle cx="12" cy="12" r="9.1" />
  <path d="M12 16.4v-4.8M12 8.2h.02" />
</>)

export const IconSpinner = make('IconSpinner', <>
  <circle cx="12" cy="12" r="8.6" opacity="0.22" />
  <path d="M20.6 12A8.6 8.6 0 0 0 12 3.4" />
</>)

export const IconBell = make('IconBell', <>
  <path d="M18.2 15.6V10.4a6.2 6.2 0 0 0-12.4 0v5.2L4 18.4h16Z" />
  <path d="M10.2 18.4a1.9 1.9 0 0 0 3.6 0" />
</>)

export const IconLock = make('IconLock', <>
  <rect x="4.6" y="10.4" width="14.8" height="10.2" rx="2.1" />
  <path d="M8.4 10.4V7.6a3.6 3.6 0 0 1 7.2 0v2.8" />
</>)

export const IconKey = make('IconKey', <>
  <circle cx="8" cy="15.6" r="3.9" />
  <path d="M10.9 12.9 20 3.8" />
  <path d="M16.6 7.2l2.3 2.3M14.4 9.4l2.3 2.3" />
</>)

export const IconBan = make('IconBan', <>
  <circle cx="12" cy="12" r="9.1" />
  <path d="M5.6 5.6 18.4 18.4" />
</>)

export const IconUser = make('IconUser', <>
  <circle cx="12" cy="8.2" r="4" />
  <path d="M4.4 20.4a7.6 7.6 0 0 1 15.2 0" />
</>)

export const IconPlug = make('IconPlug', <>
  <path d="M9 3.4v5.2M15 3.4v5.2" />
  <path d="M5.8 8.6h12.4v2.6a6.2 6.2 0 0 1-12.4 0Z" />
  <path d="M12 17.4v3.2" />
</>)

export const IconSignal = make('IconSignal', <>
  <path d="M3.6 20.4v-3.6M9.2 20.4v-7.4M14.8 20.4v-11M20.4 20.4V5.4" />
</>)

export const IconLightbulb = make('IconLightbulb', <>
  <path d="M9.4 18.2a6.4 6.4 0 1 1 5.2 0" />
  <path d="M9.6 18.2h4.8v1.6a1.4 1.4 0 0 1-1.4 1.4h-2a1.4 1.4 0 0 1-1.4-1.4Z" />
</>)

/* ── Organización ───────────────────────────────────────────────────────── */

export const IconTag = make('IconTag', <>
  <path d="M11.6 3.4H20a.6.6 0 0 1 .6.6v8.4a1.6 1.6 0 0 1-.47 1.13l-6.9 6.9a1.6 1.6 0 0 1-2.26 0l-7.53-7.53a1.6 1.6 0 0 1 0-2.26l6.9-6.9A1.6 1.6 0 0 1 11.6 3.4Z" />
  <path d="M16.6 7.4h.02" />
</>)

export const IconFolder = make('IconFolder', <>
  <path d="M3.4 6.4a1.8 1.8 0 0 1 1.8-1.8h3.7l2.1 2.6h9.6a1.8 1.8 0 0 1 1.8 1.8v8.6a1.8 1.8 0 0 1-1.8 1.8H5.2a1.8 1.8 0 0 1-1.8-1.8Z" />
</>)

export const IconLayers = make('IconLayers', <>
  <path d="M12 2.8 2.9 7.6 12 12.4l9.1-4.8Z" />
  <path d="M2.9 12.4 12 17.2l9.1-4.8" />
  <path d="M2.9 16.8 12 21.6l9.1-4.8" />
</>)

export const IconCalendar = make('IconCalendar', <>
  <rect x="3.4" y="5.2" width="17.2" height="15.4" rx="2.1" />
  <path d="M3.4 10h17.2" />
  <path d="M8.2 3.4v3.6M15.8 3.4v3.6" />
</>)

export const IconFilter = make('IconFilter', <path d="M3.4 4.6h17.2l-6.7 7.9v6.5l-3.8 2.4v-8.9Z" />)

/* ── Direccionales ──────────────────────────────────────────────────────── */

export const IconChevronDown  = make('IconChevronDown',  <path d="M6.2 9.2 12 15l5.8-5.8" />)
export const IconChevronRight = make('IconChevronRight', <path d="M9.2 6.2 15 12l-5.8 5.8" />)
export const IconChevronLeft  = make('IconChevronLeft',  <path d="M14.8 6.2 9 12l5.8 5.8" />)
export const IconChevronUp    = make('IconChevronUp',    <path d="M6.2 14.8 12 9l5.8 5.8" />)

export const IconArrowUp    = make('IconArrowUp',    <><path d="M12 19.6V4.4" /><path d="M6 10.4 12 4.4l6 6" /></>)
export const IconArrowDown  = make('IconArrowDown',  <><path d="M12 4.4v15.2" /><path d="M18 13.6 12 19.6l-6-6" /></>)
export const IconArrowLeft  = make('IconArrowLeft',  <><path d="M19.6 12H4.4" /><path d="M10.4 18 4.4 12l6-6" /></>)
export const IconArrowRight = make('IconArrowRight', <><path d="M4.4 12h15.2" /><path d="M13.6 6l6 6-6 6" /></>)

export const IconArrowUpRight   = make('IconArrowUpRight',   <><path d="M6.6 17.4 17.4 6.6" /><path d="M8.6 6.6h8.8v8.8" /></>)
export const IconArrowDownRight = make('IconArrowDownRight', <><path d="M6.6 6.6 17.4 17.4" /><path d="M17.4 8.6v8.8H8.6" /></>)

/* ── Apariencia ─────────────────────────────────────────────────────────── */

export const IconSun = make('IconSun', <>
  <circle cx="12" cy="12" r="4.2" />
  <path d="M12 2.6v2.2M12 19.2v2.2M4.36 4.36l1.56 1.56M18.08 18.08l1.56 1.56M2.6 12h2.2M19.2 12h2.2M4.36 19.64l1.56-1.56M18.08 5.92l1.56-1.56" />
</>)

export const IconMoon = make('IconMoon', <path d="M20.6 13.6A8.6 8.6 0 0 1 10.4 3.4a8.6 8.6 0 1 0 10.2 10.2Z" />)

export const IconMonitor = make('IconMonitor', <>
  <rect x="2.8" y="4" width="18.4" height="12.4" rx="2" />
  <path d="M8.6 20.4h6.8M12 16.4v4" />
</>)

export const IconSmartphone = make('IconSmartphone', <>
  <rect x="6.6" y="2.6" width="10.8" height="18.8" rx="2.4" />
  <path d="M10.8 18.4h2.4" />
</>)

export const IconDroplet = make('IconDroplet', <path d="M12 3.2 6.9 9.5a6.9 6.9 0 1 0 10.2 0Z" />)

/** Índice por nombre, útil cuando el icono se elige en tiempo de ejecución. */
export const ICONS = {
  home: IconHome, dashboard: IconDashboard, wallet: IconWallet, receipt: IconReceipt,
  chartLine: IconChartLine, chartBar: IconChartBar, chartPie: IconChartPie,
  fileText: IconFileText, trendingUp: IconTrendingUp, settings: IconSettings, menu: IconMenu,
  bank: IconBank, card: IconCard, coins: IconCoins, banknote: IconBanknote,
  briefcase: IconBriefcase, piggy: IconPiggy, store: IconStore, building: IconBuilding,
  plus: IconPlus, close: IconClose, check: IconCheck, trash: IconTrash, pencil: IconPencil,
  download: IconDownload, upload: IconUpload, refresh: IconRefresh, send: IconSend,
  link: IconLink, logout: IconLogout,
  alert: IconAlert, info: IconInfo, spinner: IconSpinner, bell: IconBell, lock: IconLock,
  key: IconKey, ban: IconBan, user: IconUser, plug: IconPlug, signal: IconSignal,
  lightbulb: IconLightbulb,
  tag: IconTag, folder: IconFolder, layers: IconLayers, calendar: IconCalendar, filter: IconFilter,
  chevronDown: IconChevronDown, chevronRight: IconChevronRight,
  chevronLeft: IconChevronLeft, chevronUp: IconChevronUp,
  arrowUp: IconArrowUp, arrowDown: IconArrowDown, arrowLeft: IconArrowLeft, arrowRight: IconArrowRight,
  arrowUpRight: IconArrowUpRight, arrowDownRight: IconArrowDownRight,
  sun: IconSun, moon: IconMoon, monitor: IconMonitor, smartphone: IconSmartphone,
  droplet: IconDroplet,
} satisfies Record<string, (props: IconProps) => ReactElement>

export type IconName = keyof typeof ICONS

/** Spinner de carga: el icono ya trae la animación aplicada. */
export function IconLoading({ size = 16, ...rest }: IconProps) {
  return <IconSpinner size={size} className="icon-spin" {...rest} />
}

/**
 * Flecha de tendencia para los badges de variación.
 *
 * Sube / baja / sin cambio.  Existe para que los tres sitios que muestran un
 * delta (KPI del Inicio, movimientos por categoría y extractos) no repitan la
 * misma cadena de ternarios con «↑ ↓ →».
 */
export function TrendArrow({ value, size = 12, ...rest }: IconProps & { value: number }) {
  if (value > 0) return <IconArrowUp size={size} {...rest} />
  if (value < 0) return <IconArrowDown size={size} {...rest} />
  return <IconArrowRight size={size} {...rest} />
}
