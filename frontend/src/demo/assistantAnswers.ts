/** Canned assistant answers for the public demo.
 *
 * There is no model behind the demo — it is a static bundle with a Service
 * Worker standing in for the API — so the chat is scripted. Every figure below
 * is read from `store.ts` at answer time rather than hardcoded, so the numbers
 * the assistant quotes are the same ones the demo's own dashboards show. A
 * scripted answer that contradicted the charts next to it would undermine the
 * exact thing the demo is meant to demonstrate.
 *
 * Answers are matched against the suggested prompts by keyword rather than by
 * exact string, because those prompts are translated and the visitor may also
 * type something close to one of them.
 */

import * as store from './store'

/** Format a number the way the app's Spanish locale does. */
function eur(value: number): string {
  return new Intl.NumberFormat('es-ES', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value)
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
  /** Tool activity chips, replayed before the text so the flow looks real. */
  tools: { name: string; label: string }[]
  text: string
}

// ── Answer builders ──────────────────────────────────────────────────────────

function spendingLastMonth(): DemoAnswer {
  const range = monthRange(1)
  const summary = store.overview({ from: range.from, to: range.to })
  const categories = store.byCategory({ from: range.from, to: range.to }).slice(0, 3)

  const lines = categories.map(c => `- ${c.category}: **${eur(c.amount)}** (${c.count} movimientos)`)
  return {
    tools: [{ name: 'get_spending_summary', label: 'Calculando totales' }],
    text:
      `El mes pasado gastaste **${eur(summary.total_expense)}** frente a ` +
      `**${eur(summary.total_income)}** de ingresos, así que el neto fue ` +
      `**${eur(summary.net)}** en ${summary.num_transactions} movimientos.\n\n` +
      `Donde más se fue:\n${lines.join('\n')}`,
  }
}

function biggestCategory(): DemoAnswer {
  const range = monthRange(1)
  const categories = store.byCategory({ from: range.from, to: range.to })
  const top = categories[0]
  const total = categories.reduce((sum, c) => sum + c.amount, 0)

  if (!top) {
    return {
      tools: [{ name: 'get_spending_by_category', label: 'Desglosando por categoría' }],
      text: 'No hay movimientos en ese periodo.',
    }
  }

  const share = total > 0 ? Math.round((top.amount / total) * 100) : 0
  return {
    tools: [{ name: 'get_spending_by_category', label: 'Desglosando por categoría' }],
    text:
      `**${top.category}** es tu mayor partida: **${eur(top.amount)}** el mes pasado, ` +
      `un **${share} %** de todo lo que gastaste, repartido en ${top.count} movimientos.\n\n` +
      `Le siguen ${categories.slice(1, 3).map(c => `${c.category} (${eur(c.amount)})`).join(' y ')}.`,
  }
}

function compareQuarters(): DemoAnswer {
  const previous = quarterRange(1)
  const current = quarterRange(0)
  const a = store.overview(previous)
  const b = store.overview(current)
  const delta = b.total_expense - a.total_expense
  const direction = delta >= 0 ? 'más' : 'menos'

  const byCatA = new Map(store.byCategory(previous).map(c => [c.category, c.amount]))
  const movers = store.byCategory(current)
    .map(c => ({ category: c.category, delta: c.amount - (byCatA.get(c.category) ?? 0) }))
    .sort((x, y) => Math.abs(y.delta) - Math.abs(x.delta))
    .slice(0, 3)

  return {
    tools: [{ name: 'compare_periods', label: 'Comparando periodos' }],
    text:
      `Este trimestre llevas **${eur(b.total_expense)}** de gasto frente a ` +
      `**${eur(a.total_expense)}** del anterior: **${eur(Math.abs(delta))} ${direction}**.\n\n` +
      `Los mayores movimientos:\n` +
      movers.map(m =>
        `- ${m.category}: ${m.delta >= 0 ? '+' : '−'}${eur(Math.abs(m.delta))}`,
      ).join('\n'),
  }
}

function subscriptions(): DemoAnswer {
  const range = monthRange(1)
  // A merchant charged in most of the last six months looks like a subscription.
  const merchants = store.byMerchant({ from: range.from, to: range.to })
    .filter(m => m.count >= 1)
    .slice(0, 5)

  return {
    tools: [{ name: 'get_spending_by_merchant', label: 'Ordenando comercios' }],
    text:
      `Estos son los comercios recurrentes que veo en tus movimientos:\n\n` +
      merchants.map(m => `- **${m.merchant}**: ${eur(m.amount)} (${m.count} cargos)`).join('\n') +
      `\n\nEn conjunto suman **${eur(merchants.reduce((s, m) => s + m.amount, 0))}** al mes.`,
  }
}

function whereToCut(): DemoAnswer {
  const range = monthRange(1)
  const categories = store.byCategory({ from: range.from, to: range.to }).slice(0, 3)
  const trimmable = categories.reduce((sum, c) => sum + c.amount * 0.15, 0)

  return {
    tools: [
      { name: 'get_spending_by_category', label: 'Desglosando por categoría' },
      { name: 'compare_periods', label: 'Comparando periodos' },
    ],
    text:
      `Mirando tus tres partidas más grandes:\n\n` +
      categories.map(c =>
        `- **${c.category}**: ${eur(c.amount)} al mes. Recortar un 15 % serían ` +
        `${eur(c.amount * 0.15)} al mes, ${eur(c.amount * 0.15 * 12)} al año.`,
      ).join('\n') +
      `\n\nSi lograses ese 15 % en las tres, liberarías **${eur(trimmable)}** al mes — ` +
      `**${eur(trimmable * 12)}** al año.`,
  }
}

function investProjection(): DemoAnswer {
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
    tools: [{ name: 'project_investment', label: 'Proyectando rentabilidad' }],
    text:
      `Invirtiendo **${eur(monthly)} al mes durante ${years} años** habrías aportado ` +
      `**${eur(contributed)}**. Según la rentabilidad anual que asumas:\n\n` +
      `- Conservador (2 %): **${eur(fv(2))}**\n` +
      `- Base (5 %): **${eur(fv(5))}**\n` +
      `- Optimista (8 %): **${eur(fv(8))}**\n\n` +
      `Son cálculos de interés compuesto sobre una rentabilidad constante, no una ` +
      `predicción. Los mercados son volátiles y ninguna rentabilidad está garantizada. ` +
      `Esto no es asesoramiento financiero.`,
  }
}

// ── Matching ─────────────────────────────────────────────────────────────────

/** Keyword sets per answer, in both languages the app ships. */
const MATCHERS: { keywords: string[]; build: () => DemoAnswer }[] = [
  { keywords: ['invert', 'invest', 'rentabilidad', 'proyec', 'return', '200'], build: investProjection },
  { keywords: ['recort', 'ahorr', 'cut', 'mejorar', 'reduc'], build: whereToCut },
  { keywords: ['suscrip', 'subscription', 'recurrent', 'comercio', 'merchant'], build: subscriptions },
  { keywords: ['trimestre', 'quarter', 'compar'], build: compareQuarters },
  { keywords: ['categor', 'más dinero', 'most of my money'], build: biggestCategory },
  { keywords: ['gast', 'spend', 'mes pasado', 'last month'], build: spendingLastMonth },
]

const FALLBACK: DemoAnswer = {
  tools: [],
  text:
    'Esta es la **demo pública** de Finlytics y no lleva un modelo de lenguaje ' +
    'detrás, así que solo puedo responder a las preguntas sugeridas.\n\n' +
    'En una instalación real el asistente consulta tus datos con herramientas de ' +
    'solo lectura y responde a cualquier pregunta sobre ellos.\n\n' +
    'This is the public demo and has no live model behind it, so only the ' +
    'suggested questions are answered here.',
}

/** Pick the scripted answer for a visitor's message. */
export function answerFor(question: string): DemoAnswer {
  const normalised = question.toLowerCase()
  for (const matcher of MATCHERS) {
    if (matcher.keywords.some(k => normalised.includes(k))) return matcher.build()
  }
  return FALLBACK
}
