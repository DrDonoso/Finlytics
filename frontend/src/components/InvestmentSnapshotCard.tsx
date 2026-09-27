import { Link } from 'react-router'
import { errorMessage } from '../api/errors'
import { useCombinedOverview } from '../api/queries'
import { getPluginLogo, pluginInitial } from '../investments/registry'
import { useT } from '../i18n'
import { IconAlert, IconLoading, IconChevronRight } from './icons'
import { Private } from './Money'
import CardHeader from './CardHeader'

export default function InvestmentSnapshotCard() {
  const { t, formatCurrency } = useT()
  const overviewQuery = useCombinedOverview()
  const loading = overviewQuery.isPending
  const error = overviewQuery.error
  const data = overviewQuery.data ?? null

  return (
    <div className="card inv-snapshot-card">
      <CardHeader
        title={t.invSnapshotTitle}
        action={<Link to="/investments" className="card-link">{t.invSnapshotGoTo} <IconChevronRight size={14} /></Link>}
      />

      {loading ? (
        <div className="state-box">
          <IconLoading size={18} />
          <span>{t.loading}</span>
        </div>
      ) : error ? (
        <div className="state-box error">
          <IconAlert size={18} />
          <span>{errorMessage(error, t)}</span>
        </div>
      ) : data && data.providers.length > 0 ? (
        <div className="inv-snapshot-body">
          <div className="inv-snapshot-total">
            <span className="inv-snapshot-total-label">{t.invCombinedTotalValue}</span>
            <span className="inv-snapshot-total-value">{data.total_value_eur == null ? '—' : <Private>{formatCurrency(data.total_value_eur)}</Private>}</span>
          </div>
          {data.partial && (
            <p className="inv-snapshot-partial">
              <IconAlert size={13} />
              <span>{t.dashboardNetWorthPartialInvestments}</span>
            </p>
          )}
          <div className="inv-snapshot-providers">
            {data.providers.map(p => (
              <Link key={p.id} to={p.route} className="inv-snapshot-provider">
                {getPluginLogo(p.id) ? (
                  <img src={getPluginLogo(p.id) ?? ''} alt="" className="plugin-logo inv-snapshot-provider-logo" />
                ) : (
                  <span className="plugin-logo-fallback inv-snapshot-provider-logo" aria-hidden="true">{pluginInitial(p.name)}</span>
                )}
                <span className="inv-snapshot-provider-name">{p.name}</span>
                <span className="inv-snapshot-provider-value">{p.value_eur == null ? '—' : <Private>{formatCurrency(p.value_eur)}</Private>}</span>
              </Link>
            ))}
          </div>
        </div>
      ) : (
        <div className="state-box">
          <span>{t.invSnapshotNoConnections}</span>
          <Link to="/investments" className="btn-secondary inv-snapshot-cta">
            {t.invSnapshotGoTo} <IconChevronRight size={14} />
          </Link>
        </div>
      )}
    </div>
  )
}
