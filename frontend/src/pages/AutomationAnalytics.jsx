import { useState, useEffect, useCallback } from 'react';
import { TrendingUp, Users, Mail, CheckCircle, Activity, Download } from 'lucide-react';
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import API from '../api';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];
const fmt = (n) => Number(n ?? 0).toLocaleString();

const StatCard = ({ icon, title, value, subtitle, color }) => {
  const colors = {
    blue:   'bg-blue-50   border-blue-200',
    green:  'bg-green-50  border-green-200',
    purple: 'bg-purple-50 border-purple-200',
    orange: 'bg-orange-50 border-orange-200',
  };
  return (
    <div className={`${colors[color]} border rounded-xl p-5`}>
      <div className="flex items-center justify-between mb-3">
        <div className="p-2 bg-white rounded-lg shadow-sm">{icon}</div>
      </div>
      <p className="text-xs font-medium text-gray-500 mb-1">{title}</p>
      <p className="text-2xl font-bold text-gray-900 tabular-nums">{typeof value === 'number' ? fmt(value) : value}</p>
      {subtitle && <p className="text-xs text-gray-500 mt-1">{subtitle}</p>}
    </div>
  );
};

export default function AutomationAnalytics() {
  const [loading, setLoading]                   = useState(true);
  const [overview, setOverview]                 = useState(null);
  const [rulesPerformance, setRulesPerformance] = useState([]);
  const [triggerComparison, setTriggerComparison] = useState([]);
  const [realtimeStats, setRealtimeStats]       = useState(null);
  const [selectedPeriod, setSelectedPeriod]     = useState(30);
  const [error, setError]                       = useState(null);
  const [exporting, setExporting]               = useState(false);

  const loadAnalytics = useCallback(async () => {
    try {
      setLoading(true); setError(null);
      const [overviewRes, performanceRes, triggerRes, realtimeRes] = await Promise.all([
        API.get(`/automation/analytics/overview?days=${selectedPeriod}`),
        API.get(`/automation/analytics/rules/performance?days=${selectedPeriod}&limit=10`),
        API.get(`/automation/analytics/triggers/comparison?days=${selectedPeriod}`),
        API.get('/automation/analytics/realtime'),
      ]);
      setOverview(overviewRes.data);
      setRulesPerformance(performanceRes.data.rules || []);
      setTriggerComparison(triggerRes.data.triggers || []);
      setRealtimeStats(realtimeRes.data);
    } catch {
      setError('Failed to load analytics data');
    } finally { setLoading(false); }
  }, [selectedPeriod]);

  useEffect(() => {
    loadAnalytics();
    const interval = setInterval(async () => {
      try {
        const res = await API.get('/automation/analytics/realtime');
        setRealtimeStats(res.data);
      } catch { /* silent */ }
    }, 30000);
    return () => clearInterval(interval);
  }, [loadAnalytics]);

  const exportCSV = async () => {
    setExporting(true);
    try {
      const response = await API.get(`/automation/analytics/export/csv?days=${selectedPeriod}`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `automation_analytics_${new Date().toISOString().split('T')[0]}.csv`);
      document.body.appendChild(link); link.click(); link.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      setError('Failed to export CSV — please try again');
    } finally { setExporting(false); }
  };

  if (loading) return (
    <div className="flex items-center justify-center py-24 gap-3 text-gray-400">
      <div className="animate-spin h-5 w-5 border-2 border-gray-300 border-t-blue-500 rounded-full" />
      Loading analytics…
    </div>
  );

  if (error) return (
    <div className="space-y-4">
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm flex items-center justify-between">
        <span>⚠️ {error}</span>
        <button onClick={loadAnalytics} className="underline ml-3 text-red-600 hover:text-red-800">Retry</button>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">

      {/* header controls */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <select value={selectedPeriod} onChange={e => setSelectedPeriod(Number(e.target.value))}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 bg-white">
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        </div>
        <button onClick={exportCSV} disabled={exporting}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50">
          <Download size={15} />
          {exporting ? 'Exporting…' : 'Export CSV'}
        </button>
      </div>

      {/* live activity banner */}
      {realtimeStats && (
        <div className="bg-gradient-to-r from-blue-600 to-purple-600 rounded-xl p-5 text-white">
          <div className="flex items-center gap-2 mb-3">
            <Activity size={18} />
            <h2 className="text-sm font-semibold">Live Activity</h2>
            <span className="ml-auto text-xs opacity-70">auto-refreshes every 30s</span>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Workflows Started (last hr)', value: realtimeStats.last_hour?.workflows_started ?? '—' },
              { label: 'Emails Sent (last hr)',        value: realtimeStats.last_hour?.emails_sent ?? '—' },
              { label: 'Active Workflows now',         value: realtimeStats.current?.active_workflows ?? '—' },
            ].map(({ label, value }) => (
              <div key={label}>
                <p className="text-xs text-blue-200 mb-1">{label}</p>
                <p className="text-2xl font-bold tabular-nums">{value}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* overview stat cards */}
      {overview && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard icon={<Users className="text-blue-600" size={20} />} title="Total Workflows"
            value={overview.workflows.total_started}
            subtitle={`${overview.workflows.completion_rate}% completion`} color="blue" />
          <StatCard icon={<CheckCircle className="text-green-600" size={20} />} title="Completed"
            value={overview.workflows.completed}
            subtitle={`${overview.workflows.in_progress} in progress`} color="green" />
          <StatCard icon={<Mail className="text-purple-600" size={20} />} title="Emails Sent"
            value={overview.emails.total_sent}
            subtitle={`${overview.emails.failure_rate}% failure rate`} color="purple" />
          <StatCard icon={<TrendingUp className="text-orange-600" size={20} />} title="Active Rules"
            value={overview.automation_rules.active}
            subtitle={`of ${overview.automation_rules.total} total`} color="orange" />
        </div>
      )}

      {/* top performing rules */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700">Top Performing Automations</h2>
        </div>
        {rulesPerformance.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-2xl mb-2">📊</p>
            <p className="text-sm text-gray-500">No performance data yet for this period</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  {['#', 'Rule Name', 'Trigger', 'Workflows', 'Emails', 'Open Rate', 'Click Rate'].map((h, i) => (
                    <th key={h} className={`px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider ${i <= 2 ? 'text-left' : 'text-right'}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {rulesPerformance.map((rule, index) => (
                  <tr key={rule.rule_id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 text-xs font-medium text-gray-400 w-8">{index + 1}</td>
                    <td className="px-4 py-3 font-medium text-gray-900">{rule.rule_name}</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 bg-blue-100 text-blue-800 text-xs rounded-full capitalize">
                        {rule.trigger}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-gray-600">{fmt(rule.workflows_started)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-gray-600">{fmt(rule.emails_sent)}</td>
                    <td className="px-4 py-3 text-right">
                      <span className={`font-medium ${rule.open_rate >= 20 ? 'text-green-600' : 'text-gray-600'}`}>
                        {rule.open_rate}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={`font-medium ${rule.click_rate >= 5 ? 'text-green-600' : 'text-gray-600'}`}>
                        {rule.click_rate}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* charts */}
      {triggerComparison.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-4">Performance by Trigger Type</h2>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={triggerComparison}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="trigger_type" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend iconSize={12} wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="workflows_started" fill="#3b82f6" name="Workflows" radius={[3, 3, 0, 0]} />
                <Bar dataKey="emails_sent"        fill="#10b981" name="Emails"    radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-4">Completion Rates by Trigger</h2>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={triggerComparison} dataKey="completion_rate" nameKey="trigger_type"
                  cx="50%" cy="50%" outerRadius={95} label={({ name, value }) => `${name}: ${value}%`} labelLine={false}>
                  {triggerComparison.map((_, i) => (
                    <Cell key={`cell-${i}`} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend iconSize={12} wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}