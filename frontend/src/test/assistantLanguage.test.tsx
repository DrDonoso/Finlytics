/** The assistant must follow the UI language.
 *
 * The demo shipped answering in Spanish regardless of the selected language,
 * and the tool activity chips were English prose from the backend, so a Spanish
 * user read "Breaking down by category" while an English user got a Spanish
 * answer. Both are the same failure: text that bypasses i18n.
 */
import { afterEach, describe, expect, it } from 'vitest'

import { answerFor } from '../demo/assistantAnswers'
import { assistantToolLabel, currentLang } from '../i18n'
import en from '../i18n/en'
import es from '../i18n/es'

const LS_KEY = 'finlytics_lang'

describe('the demo answers in the UI language', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('answers in Spanish when the UI is Spanish', () => {
    localStorage.setItem(LS_KEY, 'es')
    const answer = answerFor('cuanto gaste el mes pasado')
    expect(answer.text).toContain('El mes pasado gastaste')
  })

  it('answers in English when the UI is English', () => {
    localStorage.setItem(LS_KEY, 'en')
    const answer = answerFor('how much did I spend last month')
    expect(answer.text).toContain('Last month you spent')
    expect(answer.text).not.toContain('El mes pasado')
  })

  it('reads the language at answer time, not at import time', () => {
    // The MSW handler module is imported once, long before the visitor picks a
    // language — resolving it eagerly would freeze whatever was set on load.
    localStorage.setItem(LS_KEY, 'es')
    expect(answerFor('spend').text).toContain('El mes pasado')
    localStorage.setItem(LS_KEY, 'en')
    expect(answerFor('spend').text).toContain('Last month')
  })

  it('translates every scripted answer, not just the first', () => {
    const prompts = [
      'cuanto gaste',
      'que categoria',
      'compara el trimestre',
      'suscripciones',
      'donde recortar',
      'si invierto 200',
    ]
    localStorage.setItem(LS_KEY, 'en')
    for (const prompt of prompts) {
      const text = answerFor(prompt).text
      // A Spanish-only fragment surviving in the English build is the bug.
      expect(text).not.toMatch(/\b(gastaste|movimientos|al mes|habrías|Recortar)\b/)
    }
  })

  it('falls back in the right language too', () => {
    localStorage.setItem(LS_KEY, 'en')
    expect(answerFor('what is the capital of France').text).toContain('public demo')
    localStorage.setItem(LS_KEY, 'es')
    expect(answerFor('cual es la capital de Francia').text).toContain('demo pública')
  })

  it('formats amounts with the language locale', () => {
    localStorage.setItem(LS_KEY, 'en')
    const english = answerFor('si invierto 200').text
    localStorage.setItem(LS_KEY, 'es')
    const spanish = answerFor('si invierto 200').text
    // es-ES groups with '.', en-GB with ',' — same numbers, different rendering.
    expect(english).not.toEqual(spanish)
  })
})

describe('currentLang', () => {
  afterEach(() => localStorage.clear())

  it('prefers an explicit stored choice', () => {
    localStorage.setItem(LS_KEY, 'en')
    expect(currentLang()).toBe('en')
  })

  it('ignores a value the app does not ship', () => {
    localStorage.setItem(LS_KEY, 'fr')
    expect(['es', 'en']).toContain(currentLang())
  })
})

describe('tool activity chips', () => {
  it('translate by tool name in both languages', () => {
    // The backend sends English prose as `label`; the chip must not use it.
    expect(assistantToolLabel('get_spending_by_category', 'Breaking down by category', es))
      .toBe('Desglosando por categoría')
    expect(assistantToolLabel('get_spending_by_category', 'Breaking down by category', en))
      .toBe('Breaking down by category')
  })

  it('cover every tool the backend can report', () => {
    const names = [
      'list_reference_data', 'get_spending_summary', 'get_spending_by_category',
      'get_spending_by_month', 'get_spending_by_merchant', 'get_cashflow',
      'search_transactions', 'compare_periods', 'get_investment_overview',
      'project_investment',
    ]
    for (const name of names) {
      // Falling through to the fallback means the tool has no translation.
      expect(assistantToolLabel(name, '__FALLBACK__', es)).not.toBe('__FALLBACK__')
      expect(assistantToolLabel(name, '__FALLBACK__', en)).not.toBe('__FALLBACK__')
    }
  })

  it('falls back to the server label for an unknown tool', () => {
    // Forward compatibility: a newer backend tool should show something.
    expect(assistantToolLabel('some_future_tool', 'Doing something new', es))
      .toBe('Doing something new')
  })
})
