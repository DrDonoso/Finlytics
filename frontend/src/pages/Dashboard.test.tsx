/**
 * Tests del Inicio centrados en la degradación parcial.
 *
 * Un fallo al leer las inversiones dejaba el patrimonio total en «—», ocultando
 * también el neto de las cuentas bancarias, que sí estaba disponible. Estos
 * tests fijan que un problema en una fuente de datos no tape a otra que
 * funciona, porque es un fallo que sólo se manifiesta cuando algo va mal y por
 * tanto es fácil que vuelva sin que nadie lo note.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Dashboard from './Dashboard'
import { createQueryClient } from '../api/queryClient'
import type { AccountSummary, CombinedOverview, Overview } from '../api/types'

// ── Dobles de la capa de API ─────────────────────────────────────────────────

const getAccounts = vi.fn()
const getOverview = vi.fn()
const getOverviewMonths = vi.fn()
const getByAccount = vi.fn()
const getCombinedOverview = vi.fn()
const getStatementReminder = vi.fn()

vi.mock('../api/client', () => ({
  getAccounts: (...a: unknown[]) => getAccounts(...a),
  getOverview: (...a: unknown[]) => getOverview(...a),
  getOverviewMonths: (...a: unknown[]) => getOverviewMonths(...a),
  getByAccount: (...a: unknown[]) => getByAccount(...a),
  getCombinedOverview: (...a: unknown[]) => getCombinedOverview(...a),
  getStatementReminder: (...a: unknown[]) => getStatementReminder(...a),
}))

// La tarjeta de inversiones tiene su propia carga; aquí sólo estorba.
vi.mock('../components/InvestmentSnapshotCard', () => ({
  default: () => null,
}))

vi.mock('../contexts/NotificationsContext', () => ({
  useNotifications: () => ({ notifications: [] }),
}))

const ACCOUNTS = [
  { id: 1, name: 'BBVA', type: 'bank', currency: 'EUR', tx_count: 40, account_number_masked: '**** 4821' },
  { id: 2, name: 'Santander', type: 'bank', currency: 'EUR', tx_count: 12, account_number_masked: '**** 9032' },
]

const BY_ACCOUNT: AccountSummary[] = [
  { account: 'BBVA', expense: 1840.55, income: 5000, net: 12430.2, currency: 'EUR' },
  { account: 'Santander', expense: 210.4, income: 29110, net: 28900, currency: 'EUR' },
]

const OVERVIEW: Overview = {
  total_expense: 2050,
  total_income: 5000,
  net: 2950,
  num_transactions: 41,
  top_category: null,
  currency: 'EUR',
}

const COMBINED: CombinedOverview = {
  total_value_eur: 29670.9,
  total_invested_eur: 27000,
  total_gain_loss_eur: 2670.9,
  total_gain_loss_pct: 9.89,
  providers: [],
  by_provider: [],
  by_asset_class: [],
} as unknown as CombinedOverview

function renderDashboard() {
  // Cliente nuevo por render para aislar la caché entre tests.  Sin reintentos:
  // los tests de degradación rechazan con TypeError y el retry por defecto
  // agotaría el waitFor antes de que la query llegue a su estado de error.
  const client = createQueryClient()
  client.setDefaultOptions({
    queries: { ...client.getDefaultOptions().queries, retry: false },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Texto del bloque de patrimonio, con los espacios normalizados. */
function heroText(): string {
  const hero = document.querySelector('.dashboard-kpi-hero')
  return (hero?.textContent ?? '').replace(/\s+/g, ' ')
}

beforeEach(() => {
  vi.clearAllMocks()
  getAccounts.mockResolvedValue(ACCOUNTS)
  getByAccount.mockResolvedValue(BY_ACCOUNT)
  getOverview.mockResolvedValue(OVERVIEW)
  getOverviewMonths.mockResolvedValue({ months: ['2026-05', '2026-06'], latest: '2026-06' })
  getCombinedOverview.mockResolvedValue(COMBINED)
  getStatementReminder.mockResolvedValue({ year: null, month: null, missing_account_ids: [] })
})

// ── Camino feliz ─────────────────────────────────────────────────────────────

describe('Inicio con todas las fuentes disponibles', () => {
  it('suma cuentas e inversiones en el patrimonio', async () => {
    renderDashboard()

    // 12.430,20 + 28.900,00 + 29.670,90
    await waitFor(() => expect(heroText()).toContain('71.001,10'))
  })

  it('desglosa el patrimonio en cuentas e inversiones', async () => {
    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('71.001,10'))
    expect(heroText()).toContain('41.330,20')
    expect(heroText()).toContain('29.670,90')
  })

  it('no avisa de datos incompletos cuando no los hay', async () => {
    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('71.001,10'))
    expect(document.querySelector('.dashboard-kpi-hero__notice')).toBeNull()
  })
})

// ── Degradación parcial ──────────────────────────────────────────────────────

describe('Inicio con el conector de inversiones caído', () => {
  beforeEach(() => {
    getCombinedOverview.mockRejectedValue(new TypeError('Failed to fetch'))
  })

  it('sigue mostrando el patrimonio con lo que sí se ha podido leer', async () => {
    renderDashboard()

    // Sólo cuentas: 12.430,20 + 28.900,00. Antes esto quedaba en «—».
    await waitFor(() => expect(heroText()).toContain('41.330,20'))
  })

  it('marca las inversiones como no disponibles en lugar de contarlas como cero', async () => {
    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('41.330,20'))
    const missing = document.querySelector('.dashboard-kpi-breakdown__missing')
    expect(missing).not.toBeNull()
    expect(missing?.textContent).toBeTruthy()
  })

  it('advierte de que la cifra excluye las inversiones', async () => {
    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('41.330,20'))
    expect(document.querySelector('.dashboard-kpi-hero__notice')).not.toBeNull()
  })

  it('no suma un cero silencioso al patrimonio', async () => {
    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('41.330,20'))
    // Si contara las inversiones como 0 el total sería el mismo, pero sin aviso:
    // el usuario creería que ese es su patrimonio completo.
    expect(document.querySelector('.dashboard-kpi-hero__notice')).not.toBeNull()
  })

  it('mantiene utilizable la tabla de cuentas', async () => {
    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('41.330,20'))
    const table = document.querySelector('.dashboard-accounts-table')
    expect(table).not.toBeNull()
    expect(within(table as HTMLElement).getByText('BBVA')).toBeInTheDocument()
    expect(within(table as HTMLElement).getByText('Santander')).toBeInTheDocument()
  })
})

// ── Fallo de la fuente principal ─────────────────────────────────────────────

describe('Inicio sin poder leer las cuentas', () => {
  it('deja el patrimonio sin valor porque falta su componente principal', async () => {
    getByAccount.mockRejectedValue(new TypeError('Failed to fetch'))

    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('—'))
    // Sin cuentas no hay desglose que enseñar.
    expect(document.querySelector('.dashboard-kpi-breakdown')).toBeNull()
  })

  it('informa del fallo en la tabla de cuentas', async () => {
    getByAccount.mockRejectedValue(new TypeError('Failed to fetch'))

    renderDashboard()

    await waitFor(() => {
      expect(document.querySelector('.dashboard-accounts-card .state-box.error')).not.toBeNull()
    })
  })
})

// ── Tasa de ahorro ───────────────────────────────────────────────────────────

describe('Variación de la tasa de ahorro', () => {
  it('no se muestra cuando sólo hay un mes con datos', async () => {
    // Con un único mes no hay contra qué comparar; inventar una referencia sería
    // peor que no enseñar nada.
    getOverviewMonths.mockResolvedValue({ months: ['2026-06'], latest: '2026-06' })

    renderDashboard()

    await waitFor(() => expect(heroText()).toContain('71.001,10'))
    expect(screen.queryByText(/pp/)).toBeNull()
  })

  it('compara los dos últimos meses con datos', async () => {
    renderDashboard()

    await waitFor(() => expect(getOverview).toHaveBeenCalled())
    // Una llamada sin filtros para el histórico y una por cada mes comparado.
    await waitFor(() => {
      const ranges = getOverview.mock.calls
        .map(c => c[0])
        .filter(Boolean) as { from: string; to: string }[]
      expect(ranges).toContainEqual({ from: '2026-06-01', to: '2026-06-30' })
      expect(ranges).toContainEqual({ from: '2026-05-01', to: '2026-05-31' })
    })
  })
})
