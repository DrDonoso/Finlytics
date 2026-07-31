/** Canned assistant answers for the public demo.
 *
 * There is no model behind the demo — it is a static bundle with a Service
 * Worker standing in for the API — so the chat is scripted. Every figure below
 * is read from `store.ts` at answer time rather than hardcoded, so the numbers
 * the assistant quotes are the same ones the demo's own dashboards show. A
 * scripted answer that contradicted the charts next to it would undermine the
 * exact thing the demo is meant to demonstrate.
 *
 * Answers exist in both languages the app ships. The real assistant is told to
 * reply in whatever language the user writes in; a demo that always answered in
 * Spanish made the English build look broken, which is the one impression a
 * demo cannot afford to give.
 *
 * The language comes from `currentLang()` rather than from React context: these
 * run inside MSW handlers, at the network layer, where there is no provider.
 * `currentLang` is the same resolver the provider uses, so the mocked API can
 * never answer in a different language to the UI rendering it.
 */

import { currentLang, langLocale } from '../i18n'
import type { Lang } from '../i18n'
import * as store from './store'

/** Format an amount using the active language's locale. */
function money(value: number, lang: Lang): string {
  return new Intl.NumberFormat(langLocale(lang), {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value)
}

/** Pick one of two strings by language. */
function pick(lang: Lang, es: string, en: string): string {
  return lang === 'es' ? es : en
}

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

/** First and last day of the month N months back from today. */
function monthRange(monthsBack: number): { from: string; to: string } {
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth() - monthsBack, 1)
  const end = new Date(now.getFullYear(), now.getMonth() - monthsBack + 1, 0)
  return { from: isoDate(start), to: isoDate(end) }
}

/** Quarter boundaries, `quartersBack` quarters before the current one. */
function quarterRange(quartersBack: number): { from: string; to: string } {
  const now = new Date()
  const currentQuarterStart = Math.floor(now.getMonth() / 3) * 3
  const startMonth = currentQuarterStart - quartersBack * 3
  const start = new Date(now.getFullYear(), startMonth, 1)
  const end = new Date(now.getFullYear(), startMonth + 3, 0)
  return { from: isoDate(start), to: isoDate(end) }
}

export interface DemoAnswer {
  /** Tool activity chips, replayed before the text so the flow looks real.
   *  Only `name` matters for display — the panel translates it, and `label` is
   *  just the fallback for a tool the frontend does not recognise. */
  tools: { name: string; label: string }[]
  text: string
}

// ── Answer builders ──────────────────────────────────────────────────────────

function spendingLastMonth(lang: Lang): DemoAnswer {
  const range = monthRange(1)
  const summary = store.overview({ from: range.from, to: range.to })
  const categories = store.byCategory({ from: range.from, to: range.to }).slice(0, 3)

  const lines = categories.map(c => pick(
    lang,
    `- ${c.category}: **${money(c.amount, lang)}** (${c.count} movimientos)`,
    `- ${c.category}: **${money(c.amount, lang)}** (${c.count} transactions)`,
  ))

  return {
    tools: [{ name: 'get_spending_summary', label: 'Calculating totals' }],
    text: pick(
      lang,
      `El mes pasado gastaste **${money(summary.total_expense, lang)}** frente a `
        + `**${money(summary.total_income, lang)}** de ingresos, así que el neto fue `
        + `**${money(summary.net, lang)}** en ${summary.num_transactions} movimientos.\n\n`
        + `Donde más se fue:\n${lines.join('\n')}`,
      `Last month you spent **${money(summary.total_expense, lang)}** against `
        + `**${money(summary.total_income, lang)}** of income, so the net was `
        + `**${money(summary.net, lang)}** across ${summary.num_transactions} transactions.\n\n`
        + `Where most of it went:\n${lines.join('\n')}`,
    ),
  }
}

function biggestCategory(lang: Lang): DemoAnswer {
  const range = monthRange(1)
  const categories = store.byCategory({ from: range.from, to: range.to })
  const top = categories[0]
  const total = categories.reduce((sum, c) => sum + c.amount, 0)

  if (!top) {
    return {
      tools: [{ name: 'get_spending_by_category', label: 'Breaking down by category' }],
      text: pick(
        lang,
        'No hay movimientos en ese periodo.',
        'There are no transactions in that period.',
      ),
    }
  }

  const share = total > 0 ? Math.round((top.amount / total) * 100) : 0
  const rest = categories.slice(1, 3).map(c => `${c.category} (${money(c.amount, lang)})`)

  return {
    tools: [{ name: 'get_spending_by_category', label: 'Breaking down by category' }],
    text: pick(
      lang,
      `**${top.category}** es tu mayor partida: **${money(top.amount, lang)}** el mes `
        + `pasado, un **${share} %** de todo lo que gastaste, repartido en `
        + `${top.count} movimientos.\n\nLe siguen ${rest.join(' y ')}.`,
      `**${top.category}** is your largest area: **${money(top.amount, lang)}** last `
        + `month, **${share}%** of everything you spent, across ${top.count} `
        + `transactions.\n\nNext come ${rest.join(' and ')}.`,
    ),
  }
}

function compareQuarters(lang: Lang): DemoAnswer {
  const previous = quarterRange(1)
  const current = quarterRange(0)
  const a = store.overview(previous)
  const b = store.overview(current)
  const delta = b.total_expense - a.total_expense

  const byCatA = new Map(store.byCategory(previous).map(c => [c.category, c.amount]))
  const movers = store.byCategory(current)
    .map(c => ({ category: c.category, delta: c.amount - (byCatA.get(c.category) ?? 0) }))
    .sort((x, y) => Math.abs(y.delta) - Math.abs(x.delta))
    .slice(0, 3)

  const lines = movers.map(m =>
    `- ${m.category}: ${m.delta >= 0 ? '+' : '−'}${money(Math.abs(m.delta), lang)}`)

  return {
    tools: [{ name: 'compare_periods', label: 'Comparing periods' }],
    text: pick(
      lang,
      `Este trimestre llevas **${money(b.total_expense, lang)}** de gasto frente a `
        + `**${money(a.total_expense, lang)}** del anterior: `
        + `**${money(Math.abs(delta), lang)} ${delta >= 0 ? 'más' : 'menos'}**.\n\n`
        + `Los mayores movimientos:\n${lines.join('\n')}`,
      `This quarter you are at **${money(b.total_expense, lang)}** of spending against `
        + `**${money(a.total_expense, lang)}** last quarter: `
        + `**${money(Math.abs(delta), lang)} ${delta >= 0 ? 'more' : 'less'}**.\n\n`
        + `The biggest movements:\n${lines.join('\n')}`,
    ),
  }
}

function subscriptions(lang: Lang): DemoAnswer {
  const range = monthRange(1)
  const merchants = store.byMerchant({ from: range.from, to: range.to })
    .filter(m => m.count >= 1)
    .slice(0, 5)
  const total = merchants.reduce((s, m) => s + m.amount, 0)

  const lines = merchants.map(m => pick(
    lang,
    `- **${m.merchant}**: ${money(m.amount, lang)} (${m.count} cargos)`,
    `- **${m.merchant}**: ${money(m.amount, lang)} (${m.count} charges)`,
  ))

  return {
    tools: [{ name: 'get_spending_by_merchant', label: 'Ranking merchants' }],
    text: pick(
      lang,
      'Estos son los comercios recurrentes que veo en tus movimientos:\n\n'
        + `${lines.join('\n')}\n\nEn conjunto suman **${money(total, lang)}** al mes.`,
      'These are the recurring merchants I can see in your transactions:\n\n'
        + `${lines.join('\n')}\n\nTogether they come to **${money(total, lang)}** a month.`,
    ),
  }
}

function whereToCut(lang: Lang): DemoAnswer {
  const range = monthRange(1)
  const categories = store.byCategory({ from: range.from, to: range.to }).slice(0, 3)
  const trimmable = categories.reduce((sum, c) => sum + c.amount * 0.15, 0)

  const lines = categories.map(c => pick(
    lang,
    `- **${c.category}**: ${money(c.amount, lang)} al mes. Recortar un 15 % serían `
      + `${money(c.amount * 0.15, lang)} al mes, ${money(c.amount * 0.15 * 12, lang)} al año.`,
    `- **${c.category}**: ${money(c.amount, lang)} a month. Trimming 15% would be `
      + `${money(c.amount * 0.15, lang)} a month, ${money(c.amount * 0.15 * 12, lang)} a year.`,
  ))

  return {
    tools: [
      { name: 'get_spending_by_category', label: 'Breaking down by category' },
      { name: 'compare_periods', label: 'Comparing periods' },
    ],
    text: pick(
      lang,
      `Mirando tus tres partidas más grandes:\n\n${lines.join('\n')}\n\n`
        + `Si lograses ese 15 % en las tres, liberarías **${money(trimmable, lang)}** al `
        + `mes — **${money(trimmable * 12, lang)}** al año.`,
      `Looking at your three largest areas:\n\n${lines.join('\n')}\n\n`
        + 'If you managed that 15% across all three, you would free up '
        + `**${money(trimmable, lang)}** a month — **${money(trimmable * 12, lang)}** a year.`,
    ),
  }
}

function investProjection(lang: Lang): DemoAnswer {
  const monthly = 200
  const years = 10
  const months = years * 12

  // Same ordinary-annuity maths the real backend tool uses.
  const fv = (annualPct: number) => {
    const r = annualPct / 100 / 12
    return r === 0 ? monthly * months : monthly * (((1 + r) ** months - 1) / r)
  }
  const contributed = monthly * months

  return {
    tools: [{ name: 'project_investment', label: 'Projecting returns' }],
    text: pick(
      lang,
      `Invirtiendo **${money(monthly, lang)} al mes durante ${years} años** habrías `
        + `aportado **${money(contributed, lang)}**. Según la rentabilidad anual que `
        + 'asumas:\n\n'
        + `- Conservador (2 %): **${money(fv(2), lang)}**\n`
        + `- Base (5 %): **${money(fv(5), lang)}**\n`
        + `- Optimista (8 %): **${money(fv(8), lang)}**\n\n`
        + 'Son cálculos de interés compuesto sobre una rentabilidad constante, no una '
        + 'predicción. Los mercados son volátiles y ninguna rentabilidad está '
        + 'garantizada. Esto no es asesoramiento financiero.',
      `Investing **${money(monthly, lang)} a month for ${years} years** you would have `
        + `contributed **${money(contributed, lang)}**. Depending on the annual return `
        + 'you assume:\n\n'
        + `- Conservative (2%): **${money(fv(2), lang)}**\n`
        + `- Base (5%): **${money(fv(5), lang)}**\n`
        + `- Optimistic (8%): **${money(fv(8), lang)}**\n\n`
        + 'These are compound-interest calculations on a constant rate of return, not '
        + 'a prediction. Markets are volatile and no return is guaranteed. This is not '
        + 'financial advice.',
    ),
  }
}

// ── Matching ─────────────────────────────────────────────────────────────────

/** Keyword sets per answer, covering both languages the app ships.
 *  Matching on keywords rather than exact strings because the suggested prompts
 *  are themselves translated, and a visitor may type something close to one. */
const MATCHERS: { keywords: string[]; build: (lang: Lang) => DemoAnswer }[] = [
  { keywords: ['invert', 'invest', 'rentabilidad', 'proyec', 'return', '200'], build: investProjection },
  { keywords: ['recort', 'ahorr', 'cut back', 'cut', 'mejorar', 'reduc', 'save'], build: whereToCut },
  { keywords: ['suscrip', 'subscription', 'recurrent', 'comercio', 'merchant'], build: subscriptions },
  { keywords: ['trimestre', 'quarter', 'compar'], build: compareQuarters },
  { keywords: ['categor', 'más dinero', 'mas dinero', 'most of my money'], build: biggestCategory },
  { keywords: ['gast', 'spend', 'spent', 'mes pasado', 'last month'], build: spendingLastMonth },
]

function fallback(lang: Lang): DemoAnswer {
  return {
    tools: [],
    text: pick(
      lang,
      'Esta es la **demo pública** de Finlytics y no lleva un modelo de lenguaje '
        + 'detrás, así que solo puedo responder a las preguntas sugeridas.\n\n'
        + 'En una instalación real el asistente consulta tus datos con herramientas de '
        + 'solo lectura y responde a cualquier pregunta sobre ellos.',
      'This is the **public demo** of Finlytics and it has no language model behind '
        + 'it, so I can only answer the suggested questions.\n\n'
        + 'In a real installation the assistant queries your data with read-only tools '
        + 'and answers any question about it.',
    ),
  }
}

/** Pick the scripted answer for a visitor's message, in the UI's language. */
export function answerFor(question: string, lang: Lang = currentLang()): DemoAnswer {
  const normalised = question.toLowerCase()
  for (const matcher of MATCHERS) {
    if (matcher.keywords.some(k => normalised.includes(k))) return matcher.build(lang)
  }
  return fallback(lang)
}
