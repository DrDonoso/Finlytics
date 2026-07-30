/**
 * Tests de la comparación entre periodos.
 *
 * Es lógica pura que alimenta los badges de variación del Inicio, de Extractos y
 * de movimientos por categoría. Un error aquí no rompe nada visiblemente: sólo
 * muestra un porcentaje equivocado, que es justo el tipo de fallo que nadie
 * detecta a ojo en una aplicación de finanzas.
 */
import { describe, expect, it } from 'vitest'

import type { CategorySummary, Overview } from '../api/types'
import {
  computeDelta,
  previousCalendarMonth,
  savingsRate,
  selectTopMovers,
} from './comparison'

function overview(partial: Partial<Overview> = {}): Overview {
  return {
    total_expense: 0,
    total_income: 0,
    net: 0,
    num_transactions: 0,
    top_category: null,
    currency: 'EUR',
    ...partial,
  }
}

function category(name: string, id: number, amount: number): CategorySummary {
  return { category: name, category_id: id, amount, count: 1 }
}

// ── previousCalendarMonth ────────────────────────────────────────────────────

describe('previousCalendarMonth', () => {
  it('devuelve el mes natural anterior completo', () => {
    expect(previousCalendarMonth('2026-07-15')).toEqual({
      from: '2026-06-01',
      to: '2026-06-30',
    })
  })

  it('cruza el cambio de año', () => {
    expect(previousCalendarMonth('2026-01-09')).toEqual({
      from: '2025-12-01',
      to: '2025-12-31',
    })
  })

  it('resuelve febrero de un año bisiesto', () => {
    // 2028 es bisiesto: el mes anterior a marzo termina el día 29.
    expect(previousCalendarMonth('2028-03-01')).toEqual({
      from: '2028-02-01',
      to: '2028-02-29',
    })
  })

  it('resuelve febrero de un año no bisiesto', () => {
    expect(previousCalendarMonth('2027-03-01')).toEqual({
      from: '2027-02-01',
      to: '2027-02-28',
    })
  })

  it('devuelve null ante entradas no utilizables', () => {
    expect(previousCalendarMonth('')).toBeNull()
    expect(previousCalendarMonth('no-es-una-fecha')).toBeNull()
    expect(previousCalendarMonth('2026-13-01')).toBeNull()
    expect(previousCalendarMonth('2026-00-01')).toBeNull()
  })
})

// ── computeDelta ─────────────────────────────────────────────────────────────

describe('computeDelta', () => {
  it('calcula la variación absoluta y porcentual', () => {
    expect(computeDelta(120, 100)).toEqual({ abs: 20, pct: 20, isNew: false })
  })

  it('conserva el signo cuando el valor baja', () => {
    expect(computeDelta(80, 100)).toEqual({ abs: -20, pct: -20, isNew: false })
  })

  it('marca como nuevo lo que antes no existía', () => {
    // Sin referencia previa no hay porcentaje posible: dividir entre cero daría
    // Infinity y la interfaz mostraría «+Infinity %».
    const delta = computeDelta(50, 0)
    expect(delta).toEqual({ abs: 50, pct: null, isNew: true })
  })

  it('no marca como nuevo lo que sigue valiendo cero', () => {
    expect(computeDelta(0, 0)).toEqual({ abs: 0, pct: null, isNew: false })
  })

  it('devuelve null cuando no hay periodo anterior', () => {
    expect(computeDelta(100, null)).toBeNull()
    expect(computeDelta(100, undefined)).toBeNull()
  })

  it('trata correctamente una base negativa', () => {
    // De -100 a -50 se gasta menos, así que la variación absoluta es positiva.
    const delta = computeDelta(-50, -100)
    expect(delta?.abs).toBe(50)
    expect(delta?.pct).toBe(-50)
  })
})

// ── savingsRate ──────────────────────────────────────────────────────────────

describe('savingsRate', () => {
  it('es el neto sobre los ingresos, en porcentaje', () => {
    expect(savingsRate(overview({ total_income: 1000, net: 250 }))).toBe(25)
  })

  it('devuelve null sin ingresos', () => {
    // Sin ingresos la tasa no está definida; devolver 0 diría «no ahorras
    // nada», que no es lo mismo que «no se puede calcular».
    expect(savingsRate(overview({ total_income: 0, net: -100 }))).toBeNull()
    expect(savingsRate(overview({ total_income: -50, net: -100 }))).toBeNull()
  })

  it('admite tasas negativas cuando se gasta de más', () => {
    expect(savingsRate(overview({ total_income: 1000, net: -200 }))).toBe(-20)
  })
})

// ── selectTopMovers ──────────────────────────────────────────────────────────

describe('selectTopMovers', () => {
  it('ordena por variación absoluta en euros, no por porcentaje', () => {
    // Restauración sube un 900 % pero sólo 90 €; Vivienda sube un 25 % pero
    // 200 €. Lo relevante para el usuario es el importe.
    const movers = selectTopMovers(
      [category('Dining', 1, 100), category('Housing', 2, 1000)],
      [category('Dining', 1, 10), category('Housing', 2, 800)],
    )

    expect(movers.map(m => m.category)).toEqual(['Housing', 'Dining'])
  })

  it('tiene en cuenta las bajadas igual que las subidas', () => {
    const movers = selectTopMovers(
      [category('Dining', 1, 10)],
      [category('Dining', 1, 500)],
    )

    expect(movers[0].delta?.abs).toBe(-490)
  })

  it('devuelve vacío sin periodo anterior con el que comparar', () => {
    expect(selectTopMovers([category('Dining', 1, 100)], [])).toEqual([])
  })

  it('incluye las categorías que desaparecen del periodo actual', () => {
    // Dejar de gastar en algo es un movimiento tan informativo como empezar.
    const movers = selectTopMovers([], [category('Travel', 3, 300)])

    expect(movers).toHaveLength(1)
    expect(movers[0]).toMatchObject({ category: 'Travel', current: 0, previous: 300 })
  })

  it('marca como nuevas las categorías que no existían antes', () => {
    const movers = selectTopMovers(
      [category('Travel', 3, 300)],
      [category('Dining', 1, 10)],
    )

    const travel = movers.find(m => m.category === 'Travel')
    expect(travel?.previous).toBeNull()
    expect(travel?.delta?.isNew).toBe(true)
  })

  it('respeta el número máximo de filas pedido', () => {
    const current = Array.from({ length: 10 }, (_, i) => category(`c${i}`, i, (i + 1) * 100))
    const previous = Array.from({ length: 10 }, (_, i) => category(`c${i}`, i, 1))

    expect(selectTopMovers(current, previous, 3)).toHaveLength(3)
    expect(selectTopMovers(current, previous)).toHaveLength(5)
  })
})
