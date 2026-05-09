// frontend/src/pages/DeliverabilityDashboard.jsx
import { useState, useEffect, useCallback } from 'react';
import API from '../api';

// ── Constants ──────────────────────────────────────────────────────────────

const STATUS_META = {
  healthy:  { color: '#22c55e', bg: 'bg-green-50',  border: 'border-green-200', badge: 'bg-green-100 text-green-800',  icon: '✅' },
  warning:  { color: '#f59e0b', bg: 'bg-amber-50',  border: 'border-amber-200', badge: 'bg-amber-100 text-amber-800',  icon: '⚠️' },
  critical: { color: '#ef4444', bg: 'bg-red-50',    border: 'border-red-200',   badge: 'bg-red-100 text-red-800',     icon: '🚨' },
  info:     { color: '#3b82f6', bg: 'bg-blue-50',   border: 'border-blue-200',  badge: 'bg-blue-100 text-blue-800',   icon: 'ℹ️' },
};

const SCORE_COLORS = {
  Excellent: '#22c55e',
  Good:      '#84cc16',
  Fair:      '#f59e0b',
  Poor:      '#f97316',
  Critical:  '#ef4444',
};

const PERIOD_OPTIONS = [
  { label: '7d',  value: 7  },
  { label: '14d', value: 14 },
  { label: '30d', value: 30 },
  { label: '60d', value: 60 },
  { label: '90d', value: 90 },
];

// ── Mini sparkline (pure SVG, no deps) ────────────────────────────────────

function Sparkline({ data = [], color = '#3b82f6', thresholdValue, warningValue, height = 48, width = 200 }) {
  if (!data.length) return (
    <div style={{ height }} className="flex items-center justify-center text-gray-300 text-xs">
      No data
    </div>
  );

  const values = data.map(d => d.value);
  const maxVal = Math.max(...values, thresholdValue || 0, 0.001);
  const minVal = 0;
  const range  = maxVal - minVal || 1;
  const pad    = 4;
  const w      = width  - pad * 2;
  const h      = height - pad * 2;

  const toX = i => pad + (i / (values.length - 1 || 1)) * w;
  const toY = v => pad + h - ((v - minVal) / range) * h;

  const pts  = values.map((v, i) => `${toX(i)},${toY(v)}`).join(' ');
  const area = `M${toX(0)},${toY(0)} ` +
    values.map((v, i) => `L${toX(i)},${toY(v)}`).join(' ') +
    ` L${toX(values.length - 1)},${pad + h} L${toX(0)},${pad + h} Z`;

  const gradId = `grad-${color.replace('#', '')}`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>

      {/* Warning threshold line */}
      {thresholdValue != null && thresholdValue <= maxVal && (
        <line
          x1={pad} y1={toY(thresholdValue)} x2={pad + w} y2={toY(thresholdValue)}
          stroke="#f59e0b" strokeWidth="1" strokeDasharray="3,3" opacity="0.7"
        />
      )}
      {/* Critical threshold line */}
      {warningValue != null && warningValue <= maxVal && (
        <line
          x1={pad} y1={toY(warningValue)} x2={pad + w} y2={toY(warningValue)}
          stroke="#ef4444" strokeWidth="1" strokeDasharray="3,3" opacity="0.7"
        />
      )}

      {/* Area fill */}
      <path d={area} fill={`url(#${gradId})`} />

      {/* Line */}
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />

      {/* Last point dot */}
      <circle
        cx={toX(values.length - 1)}
        cy={toY(values[values.length - 1])}
        r="2.5"
        fill={color}
      />
    </svg>
  );
}

// ── Score gauge (SVG half-arc) ─────────────────────────────────────────────

function ScoreGauge({ score, label, color }) {
  const radius   = 70;
  const stroke   = 10;
  const cx = 90, cy = 90;
  const halfCirc = Math.PI * radius;
  const pct      = Math.min(score / 100, 1);
  const dash     = pct * halfCirc;

  const startX = cx - radius, startY = cy;
  const endX   = cx + radius, endY   = cy;

  return (
    <svg viewBox="0 0 180 100" width="200" height="120" style={{ overflow: 'visible' }}>
      {/* Track */}
      <path
        d={`M ${startX} ${startY} A ${radius} ${radius} 0 0 1 ${endX} ${endY}`}
        fill="none" stroke="#e5e7eb" strokeWidth={stroke} strokeLinecap="round"
      />
      {/* Progress */}
      <path
        d={`M ${startX} ${startY} A ${radius} ${radius} 0 0 1 ${endX} ${endY}`}
        fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
        strokeDasharray={`${dash} ${halfCirc}`}
        style={{ transition: 'stroke-dasharray 0.8s ease' }}
      />
      {/* Score text */}
      <text x={cx} y={cy - 4} textAnchor="middle" fontSize="28" fontWeight="700" fill={color}>
        {score}
      </text>
      <text x={cx} y={cy + 14} textAnchor="middle" fontSize="11" fill="#6b7280">
        / 100
      </text>
      <text x={cx} y={cy + 28} textAnchor="middle" fontSize="12" fontWeight="600" fill={color}>
        {label}
      </text>
    </svg>
  );
}

// ── Metric card with sparkline trend ──────────────────────────────────────

function MetricCard({ title, value, unit, status, trend, thresholdValue, warningValue, trendColor }) {
  const meta = STATUS_META[status] || STATUS_META.info;
  return (
    <div className={`bg-white rounded-xl border-2 ${meta.border} p-4 flex flex-col gap-2`}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-600">{title}</span>
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${meta.badge}`}>
          {meta.icon} {status}
        </span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-2xl font-bold text-gray-900">{value}</span>
        <span className="text-sm text-gray-400">{unit}</span>
      </div>
      <Sparkline
        data={trend}
        color={trendColor || meta.color}
        thresholdValue={thresholdValue}
        warningValue={warningValue}
      />
      <div className="flex justify-between text-xs text-gray-400">
        <span>30 days ago</span>
        <span>Today</span>
      </div>
    </div>
  );
}

// ── Domain table row ───────────────────────────────────────────────────────

function DomainRow({ domain }) {
  const meta   = STATUS_META[domain.status] || STATUS_META.warning;
  const checks = domain.checks || {};
  return (
    <tr className="border-b border-gray-100 last:border-0">
      <td className="py-3 pr-4 font-mono text-sm text-gray-800">{domain.domain}</td>
      <td className="py-3 pr-4">
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${meta.badge}`}>
          {meta.icon} {domain.status}
        </span>
      </td>
      <td className="py-3 pr-4">
        <div className="flex gap-2">
          {['spf', 'dkim', 'dmarc'].map(k => (
            <span
              key={k}
              title={`${k.toUpperCase()}: ${checks[k] ? 'verified' : 'not verified'}`}
              className={`text-xs font-bold px-1.5 py-0.5 rounded uppercase tracking-wide ${
                checks[k] ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-400'
              }`}
            >
              {k}
            </span>
          ))}
        </div>
      </td>
      <td className="py-3 text-xs text-gray-400">
        {domain.verified_at ? new Date(domain.verified_at).toLocaleDateString() : '—'}
      </td>
    </tr>
  );
}

// ── Recommendation card ────────────────────────────────────────────────────

function RecommendationCard({ rec }) {
  const meta = STATUS_META[rec.severity] || STATUS_META.info;
  return (
    <div className={`rounded-lg border ${meta.border} ${meta.bg} p-4`}>
      <div className="flex items-start gap-3">
        <span className="text-lg mt-0.5">{meta.icon}</span>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-gray-800 text-sm">{rec.title}</p>
          <p className="text-gray-600 text-sm mt-0.5">{rec.description}</p>
          <p className="text-gray-700 text-sm mt-1.5 font-medium">→ {rec.action}</p>
        </div>
      </div>
    </div>
  );
}

// ── Score breakdown bar ────────────────────────────────────────────────────

function ScoreBreakdownBar({ label, pts, max, status }) {
  const meta = STATUS_META[status] || STATUS_META.info;
  const pct  = max > 0 ? (pts / max) * 100 : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-gray-600 w-24 flex-shrink-0">{label}</span>
      <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
        <div
          className="h-2 rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: meta.color }}
        />
      </div>
      <span className="text-xs font-medium text-gray-500 w-14 text-right flex-shrink-0">
        {pts} / {max} pts
      </span>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function DeliverabilityDashboard() {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);
  const [days,    setDays]    = useState(30);

  const load = useCallback(async (d) => {
    setLoading(true);
    setError(null);
    try {
      const res = await API.get(`/api/deliverability/health?days=${d}`);
      setData(res.data);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to load deliverability data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(days); }, [days, load]);

  // ── Derived ──
  const score        = data?.score         ?? {};
  const metrics      = data?.metrics       ?? {};
  const trends       = data?.trends        ?? {};
  const domainHealth = data?.domain_health ?? {};
  const recs         = data?.recommendations ?? [];
  const thresholds   = metrics.thresholds  ?? {};

  const scoreColor  = SCORE_COLORS[score.label] || '#6b7280';
  const overallMeta = STATUS_META[score.overall_status] || STATUS_META.info;

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-10">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">📬 Deliverability Health</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            Sender reputation, domain verification, and rate trends
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Period selector */}
          <div className="flex bg-gray-100 rounded-lg p-0.5 gap-0.5">
            {PERIOD_OPTIONS.map(o => (
              <button
                key={o.value}
                onClick={() => setDays(o.value)}
                className={`px-3 py-1.5 text-sm rounded-md font-medium transition-colors ${
                  days === o.value
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
          <button
            onClick={() => load(days)}
            disabled={loading}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {loading ? '↻ Loading…' : '↻ Refresh'}
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">
          🚨 {error}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && !data && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 animate-pulse">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-32 bg-gray-100 rounded-xl" />
          ))}
        </div>
      )}

      {data && (
        <>
          {/* Score + breakdown */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
            <div className="flex flex-col md:flex-row items-center gap-8">

              {/* Gauge */}
              <div className="flex flex-col items-center flex-shrink-0">
                <ScoreGauge
                  score={score.total ?? 0}
                  label={score.label ?? '—'}
                  color={scoreColor}
                />
                <span className={`mt-2 text-xs font-semibold px-3 py-1 rounded-full ${overallMeta.badge}`}>
                  {overallMeta.icon} Overall: {score.overall_status}
                </span>
              </div>

              {/* Breakdown bars */}
              <div className="flex-1 w-full space-y-3">
                <h2 className="text-sm font-semibold text-gray-700 mb-1">Score Breakdown</h2>
                {[
                  { label: 'Bounce rate',    key: 'bounce'    },
                  { label: 'Complaint rate', key: 'complaint' },
                  { label: 'Unsub rate',     key: 'unsub'     },
                  { label: 'Domain health',  key: 'domain'    },
                ].map(({ label, key }) => {
                  const b = score.breakdown?.[key] ?? {};
                  return (
                    <ScoreBreakdownBar
                      key={key}
                      label={label}
                      pts={b.pts ?? 0}
                      max={b.max ?? 0}
                      status={b.status ?? 'info'}
                    />
                  );
                })}
              </div>

              {/* Quick stats */}
              <div className="grid grid-cols-2 gap-3 flex-shrink-0">
                {[
                  { label: 'Emails sent',    value: (metrics.total_sent ?? 0).toLocaleString() },
                  { label: 'Delivery rate',  value: `${metrics.delivery_rate ?? 0}%` },
                  { label: 'Bounce rate',    value: `${metrics.bounce_rate ?? 0}%` },
                  { label: 'Complaint rate', value: `${metrics.complaint_rate ?? 0}%` },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-gray-50 rounded-lg p-3 text-center">
                    <p className="text-lg font-bold text-gray-900">{value}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{label}</p>
                  </div>
                ))}
              </div>
            </div>

            <p className="text-xs text-gray-400 mt-4">
              {data._cached ? '⚡ Cached result · ' : ''}
              Last updated: {new Date(data.generated_at).toLocaleString()} ·
              Window: last {data.period_days} days
            </p>
          </div>

          {/* Metric trend cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <MetricCard
              title="Bounce Rate"
              value={metrics.bounce_rate ?? 0}
              unit="%"
              status={score.breakdown?.bounce?.status ?? 'info'}
              trend={trends.bounce_trend ?? []}
              thresholdValue={thresholds.bounce?.healthy}
              warningValue={thresholds.bounce?.warning}
              trendColor="#f59e0b"
            />
            <MetricCard
              title="Complaint Rate"
              value={metrics.complaint_rate ?? 0}
              unit="%"
              status={score.breakdown?.complaint?.status ?? 'info'}
              trend={trends.complaint_trend ?? []}
              thresholdValue={thresholds.complaint?.healthy}
              warningValue={thresholds.complaint?.warning}
              trendColor="#ef4444"
            />
          </div>

          {/* Domain health */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-gray-800">🌐 Domain Verification Status</h2>
              <div className="flex gap-3 text-sm">
                <span className="text-green-600 font-medium">✅ {domainHealth.summary?.verified ?? 0} verified</span>
                <span className="text-amber-600 font-medium">⏳ {domainHealth.summary?.pending ?? 0} pending</span>
                <span className="text-red-600 font-medium">❌ {domainHealth.summary?.failed ?? 0} failed</span>
              </div>
            </div>

            {(!domainHealth.domains || domainHealth.domains.length === 0) ? (
              <div className="text-center py-8 text-gray-400">
                <p className="text-3xl mb-2">🌐</p>
                <p className="text-sm">No domains configured.</p>
                <a href="/settings/domain" className="text-blue-600 text-sm hover:underline mt-1 inline-block">
                  Go to Domain Settings →
                </a>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-gray-400 border-b border-gray-100">
                      <th className="pb-2 pr-4 font-medium">Domain</th>
                      <th className="pb-2 pr-4 font-medium">Status</th>
                      <th className="pb-2 pr-4 font-medium">DNS Records</th>
                      <th className="pb-2 font-medium">Verified</th>
                    </tr>
                  </thead>
                  <tbody>
                    {domainHealth.domains.map(d => (
                      <DomainRow key={d.domain} domain={d} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="mt-4 pt-4 border-t border-gray-100 text-right">
              <a href="/settings/domain" className="text-blue-600 text-sm hover:underline">
                Manage domains →
              </a>
            </div>
          </div>

          {/* Recommendations */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
            <h2 className="font-semibold text-gray-800 mb-4">💡 Recommendations</h2>
            <div className="space-y-3">
              {recs.map((rec, i) => (
                <RecommendationCard key={i} rec={rec} />
              ))}
            </div>
          </div>

          {/* Industry reference */}
          <div className="bg-gray-50 border border-gray-200 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">📏 Industry Thresholds Reference</h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs text-gray-600">
              <div>
                <p className="font-semibold mb-1">Bounce Rate</p>
                <p><span className="text-green-600 font-medium">Healthy:</span> &lt; 2%</p>
                <p><span className="text-amber-600 font-medium">Warning:</span> 2–5%</p>
                <p><span className="text-red-600 font-medium">Critical:</span> &gt; 5%</p>
              </div>
              <div>
                <p className="font-semibold mb-1">Spam Complaint Rate</p>
                <p><span className="text-green-600 font-medium">Healthy:</span> &lt; 0.08%</p>
                <p><span className="text-amber-600 font-medium">Warning:</span> 0.08–0.1%</p>
                <p><span className="text-red-600 font-medium">Critical:</span> &gt; 0.1%</p>
                <p className="text-gray-400 mt-1">Google/Yahoo 2024 requirement</p>
              </div>
              <div>
                <p className="font-semibold mb-1">Unsubscribe Rate</p>
                <p><span className="text-green-600 font-medium">Healthy:</span> &lt; 0.5%</p>
                <p><span className="text-amber-600 font-medium">Warning:</span> 0.5–1%</p>
                <p><span className="text-red-600 font-medium">Critical:</span> &gt; 1%</p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
