/**
 * Verifica que una respuesta lenta de un filtro anterior no puede pisar a la del
 * filtro activo.
 *
 * Es el fallo que motivó migrar las peticiones a consultas con clave: al cambiar
 * de periodo rápido, el patrón anterior (useEffect + setState) dejaba en
 * pantalla los datos de la primera petición si esta respondía después que la
 * segunda. No lanza ningún error, sólo muestra cifras que no se corresponden con
 * el filtro seleccionado, así que es prácticamente indetectable a ojo.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from './queryClient'
import { useOverview } from './queries'
import type { Overview, SummaryParams } from './types'

const getOverview = vi.fn()

vi.mock('./client', () => ({
  getAccounts: vi.fn(),
  getByAccount: vi.fn(),
  getByCategory: vi.fn(),
  getByDay: vi.fn(),
  getByMerchant: vi.fn(),
  getByMonth: vi.fn(),
  getCashflow: vi.fn(),
  getCategories: vi.fn(),
  getCombinedOverview: vi.fn(),
  getConnections: vi.fn(),
  getOverview: (...a: unknown[]) => getOverview(...a),
  getOverviewMonths: vi.fn(),
  getRules: vi.fn(),
  getStatementMonths: vi.fn(),
  getStatementReminder: vi.fn(),
  getTags: vi.fn(),
}))

function overview(totalExpense: number): Overview {
  return {
    total_expense: totalExpense,
    total_income: 0,
    net: 0,
    num_transactions: 0,
    top_category: null,
    currency: 'EUR',
  }
}

/** Muestra el gasto del periodo pedido, para poder ver qué respuesta ganó. */
function Probe({ params }: { params: SummaryParams }) {
  const { data, isPending } = useOverview(params)
  if (isPending) return <span data-testid="value">cargando</span>
  return <span data-testid="value">{data?.total_expense ?? 'sin datos'}</span>
}

function wrapper(children: ReactNode) {
  const client = createQueryClient()
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useOverview con filtros que cambian', () => {
  it('descarta la respuesta del filtro anterior aunque llegue la última', async () => {
    const MAYO = { from: '2026-05-01', to: '2026-05-31' }
    const JULIO = { from: '2026-07-01', to: '2026-07-31' }

    let resolveMayo: (v: Overview) => void = () => {}
    getOverview.mockImplementation((params: SummaryParams) => {
      if (params.from === MAYO.from) {
        // Mayo se queda colgado a propósito: responderá el último.
        return new Promise<Overview>(resolve => { resolveMayo = resolve })
      }
      return Promise.resolve(overview(7000))
    })

    const { rerender } = render(wrapper(<Probe params={MAYO} />))
    expect(await screen.findByText('cargando')).toBeInTheDocument()

    // El usuario cambia a julio antes de que mayo haya respondido.
    rerender(wrapper(<Probe params={JULIO} />))
    await waitFor(() => expect(screen.getByTestId('value')).toHaveTextContent('7000'))

    // Y ahora, tarde, llega la respuesta de mayo.
    resolveMayo(overview(5000))
    await new Promise(r => setTimeout(r, 50))

    // La pantalla debe seguir mostrando julio, que es el filtro activo.
    expect(screen.getByTestId('value')).toHaveTextContent('7000')
    expect(screen.getByTestId('value')).not.toHaveTextContent('5000')
  })

  it('cachea por parámetros en lugar de volver a pedir lo mismo', async () => {
    getOverview.mockResolvedValue(overview(1234))
    const params = { from: '2026-06-01', to: '2026-06-30' }

    const client = createQueryClient()
    const view = (
      <QueryClientProvider client={client}>
        <Probe params={params} />
        <Probe params={params} />
      </QueryClientProvider>
    )

    render(view)
    await waitFor(() => {
      expect(screen.getAllByTestId('value')[0]).toHaveTextContent('1234')
    })

    // Dos componentes pidiendo lo mismo antes hacían dos peticiones.
    expect(getOverview).toHaveBeenCalledTimes(1)
  })

  it('distingue periodos distintos en la caché', async () => {
    getOverview.mockImplementation((params: SummaryParams) =>
      Promise.resolve(overview(params.from === '2026-05-01' ? 5000 : 7000)),
    )

    const client = createQueryClient()
    render(
      <QueryClientProvider client={client}>
        <Probe params={{ from: '2026-05-01', to: '2026-05-31' }} />
        <Probe params={{ from: '2026-07-01', to: '2026-07-31' }} />
      </QueryClientProvider>,
    )

    await waitFor(() => {
      const values = screen.getAllByTestId('value').map(n => n.textContent)
      expect(values).toContain('5000')
      expect(values).toContain('7000')
    })
    expect(getOverview).toHaveBeenCalledTimes(2)
  })
})

describe('el patrón anterior sí se corrompía', () => {
  /**
   * Reproduce el useEffect + setState que había antes, para dejar constancia de
   * que el fallo era real y no una precaución teórica. Si este test dejara de
   * fallar en su versión sin proteger, la migración no habría hecho falta.
   */
  function LegacyProbe({ params }: { params: SummaryParams }) {
    const [value, setValue] = useState<number | null>(null)

    useEffect(() => {
      setValue(null)
      getOverview(params).then((d: Overview) => setValue(d.total_expense))
    }, [params])

    return <span data-testid="legacy">{value === null ? 'cargando' : value}</span>
  }

  it('deja en pantalla los datos del filtro que ya no está activo', async () => {
    const MAYO = { from: '2026-05-01', to: '2026-05-31' }
    const JULIO = { from: '2026-07-01', to: '2026-07-31' }

    let resolveMayo: (v: Overview) => void = () => {}
    getOverview.mockImplementation((params: SummaryParams) => {
      if (params.from === MAYO.from) {
        return new Promise<Overview>(resolve => { resolveMayo = resolve })
      }
      return Promise.resolve(overview(7000))
    })

    const { rerender } = render(<LegacyProbe params={MAYO} />)
    rerender(<LegacyProbe params={JULIO} />)
    await waitFor(() => expect(screen.getByTestId('legacy')).toHaveTextContent('7000'))

    // Llega tarde la respuesta de mayo...
    resolveMayo(overview(5000))

    // ...y pisa la de julio: la pantalla muestra mayo con el filtro en julio.
    await waitFor(() => expect(screen.getByTestId('legacy')).toHaveTextContent('5000'))
  })
})
