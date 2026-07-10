import { useMemo, useCallback } from 'react'
import { Sankey, ResponsiveContainer, Tooltip } from 'recharts'
import type { Category, CashflowSummary } from '../api/types'
import { useT, categoryLabel, formatCurrency } from '../i18n'

type NodeType = 'income' | 'center' | 'expense'

interface SankeyNodeDatum {
  name: string
  type: NodeType
  amount: number
  category_id?: number
}

// Custom link renderer — creates smooth ribbon between nodes
function SankeyLink(props: any) {
  const {
    sourceX, targetX, sourceY, targetY,
    sourceControlX, targetControlX, linkWidth, payload,
  } = props
  if (!linkWidth) return null

  const isIncome = payload?.source?.type === 'income'
  const fill   = isIncome ? 'rgba(34,197,94,0.16)'  : 'rgba(239,68,68,0.12)'
  const stroke = isIncome ? 'rgba(34,197,94,0.32)'  : 'rgba(239,68,68,0.22)'
  const half = linkWidth / 2

  return (
    <path
      d={`M${sourceX},${sourceY + half}
          C${sourceControlX},${sourceY + half} ${targetControlX},${targetY + half} ${targetX},${targetY + half}
          L${targetX},${targetY - half}
          C${targetControlX},${targetY - half} ${sourceControlX},${sourceY - half} ${sourceX},${sourceY - half}Z`}
      fill={fill}
      stroke={stroke}
      strokeWidth={1}
    />
  )
}

function SankeyTooltip({ active, payload }: any) {
  const { lang } = useT()
  if (!active || !payload?.length) return null
  const p = payload[0]
  const amount = p.payload?.payload?.amount ?? p.value ?? 0
  const name   = p.name ?? p.payload?.payload?.name ?? ''
  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 8,
      padding: '8px 12px',
      fontSize: 12,
      boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
    }}>
      <div style={{ fontWeight: 600, marginBottom: 2, color: 'var(--text)' }}>{name}</div>
      <div style={{ color: 'var(--text-muted)' }}>{formatCurrency(amount, lang)}</div>
    </div>
  )
}

interface Props {
  data: CashflowSummary | null
  loading: boolean
  error: string | null
  categories: Category[]
  selectedCategoryId?: number
  onCategoryClick: (id: number | undefined) => void
}

export default function CashflowSankey({ data, loading, error, categories, selectedCategoryId, onCategoryClick }: Props) {
  const { t, lang, formatCurrency: fmtCur } = useT()

  const sankeyData = useMemo(() => {
    if (!data || (data.income.length === 0 && data.expense.length === 0)) return null

    function resolveCategoryId(canonicalName: string): number | undefined {
      return categories.find(c => c.name === canonicalName)?.id
    }

    const incomeNodes: SankeyNodeDatum[] = data.income.map(i => ({
      name:        categoryLabel(i.category, lang),
      type:        'income' as const,
      amount:      i.amount,
      category_id: resolveCategoryId(i.category),
    }))
    const centerIdx = incomeNodes.length
    const centerNode: SankeyNodeDatum = {
      name:   t.cashflowNode,
      type:   'center' as const,
      amount: data.total_income,
    }
    const expenseNodes: SankeyNodeDatum[] = data.expense.map(e => ({
      name:        categoryLabel(e.category, lang),
      type:        'expense' as const,
      amount:      e.amount,
      category_id: resolveCategoryId(e.category),
    }))

    const nodes: SankeyNodeDatum[] = [...incomeNodes, centerNode, ...expenseNodes]
    const links = [
      ...data.income.map((item, i) => ({
        source: i,
        target: centerIdx,
        value:  item.amount,
      })),
      ...data.expense.map((item, i) => ({
        source: centerIdx,
        target: centerIdx + 1 + i,
        value:  item.amount,
      })),
    ]
    return { nodes, links }
  }, [data, lang, t.cashflowNode, categories])

  // Custom node renderer with clickable labels and enlarged hit areas
  const renderSankeyNode = useCallback((props: any) => {
    const { x, y, width, height, payload } = props
    if (x == null || y == null || !payload) return null

    const isCenter    = payload.type === 'center'
    const isIncome    = payload.type === 'income'
    const isClickable = !isCenter && payload.category_id !== undefined
    const isSelected  = isClickable && selectedCategoryId === payload.category_id
    const isDimmed    = selectedCategoryId !== undefined && isClickable && !isSelected

    // Node fill using CSS vars (interpreted by the browser during paint)
    const nodeColor = isIncome ? 'var(--income)' : isCenter ? 'var(--primary)' : 'var(--expense)'

    // Label positioning
    const onRight     = payload.type === 'expense'
    const labelX      = isCenter ? x + width / 2 : onRight ? x + width + 8 : x - 8
    const labelAnchor = isCenter ? 'middle' : onRight ? 'start' : 'end'

    // For two-line labels: center the block vertically on the node's midpoint
    // Line 1 at baseY, line 2 at baseY + 14px
    const lineBaseY = y + height / 2 - 7

    function handleClick() {
      if (!isClickable) return
      onCategoryClick(selectedCategoryId === payload.category_id ? undefined : payload.category_id)
    }

    // Transparent hit area around the label text (~160 × 36 px)
    const hitW = 162
    const hitH = 38
    const hitX = onRight
      ? labelX - 4
      : Math.max(0, labelX - hitW + 4)
    const hitY = lineBaseY - 10

    return (
      <g>
        {/* ── Node rectangle ── */}
        <rect
          x={x}
          y={y}
          width={width}
          height={Math.max(height, 1)}
          rx={3}
          fill={nodeColor}
          fillOpacity={isDimmed ? 0.22 : 0.88}
          stroke={isSelected ? nodeColor : 'none'}
          strokeWidth={isSelected ? 3 : 0}
          onClick={isClickable ? handleClick : undefined}
          style={{ cursor: isClickable ? 'pointer' : 'default' }}
        />

        {/* ── Center node: single label above ── */}
        {isCenter && (
          <text
            x={labelX}
            y={y - 10}
            textAnchor={labelAnchor}
            fontSize={12}
            fontWeight={600}
            fill="var(--text)"
            style={{ pointerEvents: 'none' }}
          >
            {payload.name}
          </text>
        )}

        {/* ── Income / Expense: two-line label + enlarged hit area ── */}
        {!isCenter && (
          <g
            onClick={isClickable ? handleClick : undefined}
            style={{ cursor: isClickable ? 'pointer' : 'default' }}
          >
            {/* Transparent click target */}
            {isClickable && (
              <rect
                x={hitX}
                y={hitY}
                width={hitW}
                height={hitH}
                fill="transparent"
              />
            )}
            {/* Category name */}
            <text
              x={labelX}
              y={lineBaseY}
              textAnchor={labelAnchor}
              fontSize={11}
              fontWeight={isSelected ? 700 : 500}
              fill="var(--text)"
              style={{ pointerEvents: 'none' }}
            >
              {payload.name}
            </text>
            {/* Amount */}
            <text
              x={labelX}
              y={lineBaseY + 14}
              textAnchor={labelAnchor}
              fontSize={10}
              fill="var(--text-muted)"
              style={{ pointerEvents: 'none' }}
            >
              {fmtCur(payload.amount)}
            </text>
          </g>
        )}
      </g>
    )
  }, [selectedCategoryId, onCategoryClick, fmtCur])

  return (
    <div className="card cashflow-card">
      <div className="card-title">{t.chartCashflow}</div>

      {error && (
        <div className="state-box error">
          <span className="icon">⚠</span>
          <span>{error}</span>
        </div>
      )}

      {!error && loading && (
        <div className="state-box">
          <span className="icon">⏳</span>
          <span>{t.loading}</span>
        </div>
      )}

      {!error && !loading && !sankeyData && (
        <div className="state-box">
          <span className="icon">📊</span>
          <span>{t.noDataPeriod}</span>
        </div>
      )}

      {!error && !loading && sankeyData && (
        <div>
          <div className="cashflow-totals">
            <span style={{ color: 'var(--income)' }}>
              ↑ {fmtCur(data!.total_income)} {t.legendIncome}
            </span>
            <span style={{ color: 'var(--expense)' }}>
              ↓ {fmtCur(data!.total_expense)} {t.legendExpense}
            </span>
          </div>
          <div className="sankey-scroll-wrapper">
            <div className="sankey-inner">
              <ResponsiveContainer width="100%" height={420}>
                <Sankey
                  data={sankeyData as any}
                  node={renderSankeyNode as any}
                  link={SankeyLink as any}
                  nodePadding={22}
                  nodeWidth={14}
                  margin={{ left: 172, right: 172, top: 32, bottom: 32 }}
                  sort={false}
                >
                  <Tooltip content={<SankeyTooltip />} />
                </Sankey>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
