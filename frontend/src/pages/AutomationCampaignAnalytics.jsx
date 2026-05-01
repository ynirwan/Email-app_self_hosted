import { useState, useEffect, useCallback } from 'react';
import { BarChart3, TrendingUp, Mail, Users, ArrowLeft } from 'lucide-react';
import { useSettings } from "../contexts/SettingsContext";
import { useParams, useNavigate } from 'react-router-dom';
import API from '../api';

const fmt = (n) => Number(n ?? 0).toLocaleString();

const RateBar = ({ value, max = 60, color = 'bg-blue-500' }) => (
  <div className="flex items-center gap-2 mt-1">
    <div className="flex-1 bg-gray-100 rounded-full h-1.5">
      <div className={`${color} h-1.5 rounded-full`} style={{ width: `${Math.min((value / max) * 100, 100)}%` }} />
    </div>
    <span className="text-xs tabular-nums text-gray-600 w-12">{value.toFixed(1)}%</span>
  </div>
);

export default function AutomationCampaignAnalytics() {
  const { t, formatDate } = useSettings();
  const { id } = useParams();
  const navigate = useNavigate();

  const [analytics, setAnalytics]           = useState(null);
  const [automationName, setAutomationName] = useState('');
  const [loading, setLoading]               = useState(true);
  const [error, setError]                   = useState(null);

  const fetchAnalytics = useCallback(async () => {
    if (!id) return;
    try {
      setLoading(true); setError(null);
      const res = await API.get(`/automation/rules/${id}/analytics`);
      const data = res?.data || res;
      setAnalytics(data);
      setAutomationName(data.rule_name || 'Automation Analytics');
    } catch {
      setError('Failed to load analytics data');
    } finally { setLoading(false); }
  }, [id]);

  useEffect(() => { fetchAnalytics(); }, [fetchAnalytics]);

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
        <button onClick={fetchAnalytics} className="underline ml-3">Retry</button>
      </div>
      <button onClick={() => navigate('/automation')}
        className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600">
        <ArrowLeft size={14} /> Back to Automations
      </button>
    </div>
  );

  if (!analytics) return (
    <div className="py-16 text-center">
      <BarChart3 size={48} className="mx-auto text-gray-300 mb-3" />
      <p className="text-sm text-gray-500">No analytics data available</p>
      <button onClick={() => navigate('/automation')}
        className="mt-4 flex items-center gap-2 px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600 mx-auto">
        <ArrowLeft size={14} /> Back to Automations
      </button>
    </div>
  );

  return (
    <div className="space-y-6">

      {/* header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <button onClick={() => navigate('/automation')}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 mb-1.5">
            <ArrowLeft size={12} /> Automations
          </button>
          <p className="text-base font-semibold text-gray-900">{automationName}</p>
          <p className="text-xs text-gray-400 mt-0.5">Performance analytics</p>
        </div>
        <button onClick={fetchAnalytics}
          className="px-4 py-2 border border-gray-200 text-sm font-medium rounded-lg hover:bg-gray-50 text-gray-600">
          🔄 Refresh
        </button>
      </div>

      {/* key metric cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          {
            icon: <Mail className="text-blue-600" size={20} />,
            label: t('analytics.totalSent'), value: fmt(analytics.emails_sent),
            sub: null, bg: 'bg-blue-50 border-blue-200',
          },
          {
            icon: <TrendingUp className="text-green-600" size={20} />,
            label: t('analytics.openRate'), value: `${(analytics.open_rate || 0).toFixed(1)}%`,
            sub: `${fmt(analytics.emails_opened)} ${t('analytics.opens')}`,
            bg: 'bg-green-50 border-green-200',
            bar: <RateBar value={analytics.open_rate || 0} color="bg-green-500" />,
          },
          {
            icon: <BarChart3 className="text-purple-600" size={20} />,
            label: t('analytics.clickRate'), value: `${(analytics.click_rate || 0).toFixed(1)}%`,
            sub: `${fmt(analytics.emails_clicked)} ${t('analytics.clicks')}`,
            bg: 'bg-purple-50 border-purple-200',
            bar: <RateBar value={analytics.click_rate || 0} color="bg-purple-500" />,
          },
          {
            icon: <Users className="text-orange-600" size={20} />,
            label: t('automation.analytics.enrolled') || 'Subscribers Entered', value: fmt(analytics.subscribers_entered),
            sub: `${fmt(analytics.subscribers_completed)} ${t('automation.analytics.completed') || 'completed'}`,
            bg: 'bg-orange-50 border-orange-200',
          },
        ].map(({ icon, label, value, sub, bg, bar }) => (
          <div key={label} className={`${bg} border rounded-xl p-5`}>
            <div className="flex items-center gap-2 mb-3">
              <div className="p-1.5 bg-white rounded-lg shadow-sm">{icon}</div>
            </div>
            <p className="text-xs font-medium text-gray-500 mb-1">{label}</p>
            <p className="text-2xl font-bold text-gray-900 tabular-nums">{value}</p>
            {bar}
            {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
          </div>
        ))}
      </div>

      {/* execution stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { label: 'Total Executions',     value: analytics.total_executions     || 0, color: 'text-gray-900', bg: 'bg-white' },
          { label: 'Completed',            value: analytics.completed_executions || 0, color: 'text-green-600', bg: 'bg-green-50 border-green-100' },
          { label: 'Failed',               value: analytics.failed_executions    || 0, color: 'text-red-600',   bg: 'bg-red-50 border-red-100' },
        ].map(({ label, value, color, bg }) => (
          <div key={label} className={`${bg} border border-gray-200 rounded-xl p-5`}>
            <p className="text-xs font-medium text-gray-500 mb-2">{label}</p>
            <p className={`text-3xl font-bold tabular-nums ${color}`}>{fmt(value)}</p>
          </div>
        ))}
      </div>

      {/* email step performance */}
      {analytics.email_performance?.length > 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-700">Email Step Performance</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Step</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-20">Sent</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-20">Opens</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-20">Clicks</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-24">Open Rate</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-24">Click Rate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {analytics.email_performance.map((email, index) => (
                  <tr key={index} className="hover:bg-gray-50 transition-colors">
                    <td className="px-5 py-3.5 font-medium text-gray-900">
                      {email.subject || `Step ${index + 1}`}
                    </td>
                    <td className="px-4 py-3.5 text-right tabular-nums text-gray-600">{fmt(email.sent)}</td>
                    <td className="px-4 py-3.5 text-right tabular-nums text-gray-600">{fmt(email.opens)}</td>
                    <td className="px-4 py-3.5 text-right tabular-nums text-gray-600">{fmt(email.clicks)}</td>
                    <td className="px-4 py-3.5 text-right">
                      <span className={`font-medium tabular-nums ${(email.open_rate || 0) >= 20 ? 'text-green-600' : 'text-gray-600'}`}>
                        {(email.open_rate || 0).toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <span className={`font-medium tabular-nums ${(email.click_rate || 0) >= 5 ? 'text-green-600' : 'text-gray-600'}`}>
                        {(email.click_rate || 0).toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="bg-gray-50 border border-dashed border-gray-200 rounded-xl p-10 text-center">
          <BarChart3 size={40} className="mx-auto text-gray-300 mb-3" />
          <p className="text-sm font-medium text-gray-500">No email step data yet</p>
          <p className="text-xs text-gray-400 mt-1">Will appear once emails start sending</p>
        </div>
      )}
    </div>
  );
}