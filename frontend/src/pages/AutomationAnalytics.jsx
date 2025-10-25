// frontend/src/pages/AutomationAnalytics.jsx
import React, { useState, useEffect } from 'react';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import {
  TrendingUp, Users, Mail, CheckCircle, XCircle,
  Clock, DollarSign, Activity, Download
} from 'lucide-react';
import API from '../api';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];

const AutomationAnalytics = () => {
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState(null);
  const [rulesPerformance, setRulesPerformance] = useState([]);
  const [triggerComparison, setTriggerComparison] = useState([]);
  const [realtimeStats, setRealtimeStats] = useState(null);
  const [selectedPeriod, setSelectedPeriod] = useState(30);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadAnalytics();

    // Refresh realtime stats every 30 seconds
    const interval = setInterval(loadRealtimeStats, 30000);
    return () => clearInterval(interval);
  }, [selectedPeriod]);

  const loadAnalytics = async () => {
    try {
      setLoading(true);
      setError(null);

      const [overviewRes, performanceRes, triggerRes, realtimeRes] = await Promise.all([
        API.get(`/automation/analytics/overview?days=${selectedPeriod}`),
        API.get(`/automation/analytics/rules/performance?days=${selectedPeriod}&limit=10`),
        API.get(`/automation/analytics/triggers/comparison?days=${selectedPeriod}`),
        API.get('/automation/analytics/realtime')
      ]);

      setOverview(overviewRes.data);
      setRulesPerformance(performanceRes.data.rules || []);
      setTriggerComparison(triggerRes.data.triggers || []);
      setRealtimeStats(realtimeRes.data);

    } catch (err) {
      console.error('Failed to load analytics:', err);
      setError('Failed to load analytics data');
    } finally {
      setLoading(false);
    }
  };

  const loadRealtimeStats = async () => {
    try {
      const res = await API.get('/automation/analytics/realtime');
      setRealtimeStats(res.data);
    } catch (err) {
      console.error('Failed to load realtime stats:', err);
    }
  };

  const exportCSV = async () => {
    try {
      const response = await API.get(`/automation/analytics/export/csv?days=${selectedPeriod}`, {
        responseType: 'blob'
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `automation_analytics_${new Date().toISOString().split('T')[0]}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error('Failed to export CSV:', err);
      alert('Failed to export analytics');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading analytics...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Automation Analytics</h1>
          <p className="text-gray-600 mt-1">Performance insights and metrics</p>
        </div>

        <div className="flex gap-3">
          <select
            value={selectedPeriod}
            onChange={(e) => setSelectedPeriod(Number(e.target.value))}
            className="px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value={7}>Last 7 Days</option>
            <option value={30}>Last 30 Days</option>
            <option value={90}>Last 90 Days</option>
          </select>

          <button
            onClick={exportCSV}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
          >
            <Download size={18} />
            Export CSV
          </button>
        </div>
      </div>

      {/* Realtime Stats */}
      {realtimeStats && (
        <div className="bg-gradient-to-r from-blue-500 to-purple-600 rounded-lg p-6 text-white">
          <div className="flex items-center gap-2 mb-4">
            <Activity size={24} />
            <h2 className="text-xl font-semibold">Live Activity</h2>
          </div>
          <div className="grid grid-cols-3 gap-6">
            <div>
              <p className="text-blue-100 text-sm">Last Hour</p>
              <p className="text-3xl font-bold">{realtimeStats.last_hour.workflows_started}</p>
              <p className="text-sm">Workflows Started</p>
            </div>
            <div>
              <p className="text-blue-100 text-sm">Last Hour</p>
              <p className="text-3xl font-bold">{realtimeStats.last_hour.emails_sent}</p>
              <p className="text-sm">Emails Sent</p>
            </div>
            <div>
              <p className="text-blue-100 text-sm">Currently</p>
              <p className="text-3xl font-bold">{realtimeStats.current.active_workflows}</p>
              <p className="text-sm">Active Workflows</p>
            </div>
          </div>
        </div>
      )}

      {/* Overview Cards */}
      {overview && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <StatCard
            icon={<Users className="text-blue-600" size={24} />}
            title="Total Workflows"
            value={overview.workflows.total_started}
            subtitle={`${overview.workflows.completion_rate}% completion rate`}
            color="blue"
          />
          <StatCard
            icon={<CheckCircle className="text-green-600" size={24} />}
            title="Completed"
            value={overview.workflows.completed}
            subtitle={`${overview.workflows.in_progress} in progress`}
            color="green"
          />
          <StatCard
            icon={<Mail className="text-purple-600" size={24} />}
            title="Emails Sent"
            value={overview.emails.total_sent}
            subtitle={`${overview.emails.failure_rate}% failure rate`}
            color="purple"
          />
          <StatCard
            icon={<TrendingUp className="text-orange-600" size={24} />}
            title="Active Rules"
            value={overview.automation_rules.active}
            subtitle={`of ${overview.automation_rules.total} total`}
            color="orange"
          />
        </div>
      )}

      {/* Top Performing Rules */}
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <h2 className="text-xl font-semibold mb-4">Top Performing Automations</h2>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-3 px-4">Rule Name</th>
                <th className="text-left py-3 px-4">Trigger</th>
                <th className="text-right py-3 px-4">Workflows</th>
                <th className="text-right py-3 px-4">Emails Sent</th>
                <th className="text-right py-3 px-4">Open Rate</th>
                <th className="text-right py-3 px-4">Click Rate</th>
                <th className="text-right py-3 px-4">Revenue</th>
              </tr>
            </thead>
            <tbody>
              {rulesPerformance.map((rule, index) => (
                <tr key={rule.rule_id} className="border-b hover:bg-gray-50">
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-700">{index + 1}.</span>
                      <span className="font-medium">{rule.rule_name}</span>
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    <span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded-full">
                      {rule.trigger}
                    </span>
                  </td>
                  <td className="text-right py-3 px-4">{rule.workflows_started}</td>
                  <td className="text-right py-3 px-4">{rule.emails_sent}</td>
                  <td className="text-right py-3 px-4">
                    <span className={`font-medium ${rule.open_rate >= 20 ? 'text-green-600' : 'text-gray-600'}`}>
                      {rule.open_rate}%
                    </span>
                  </td>
                  <td className="text-right py-3 px-4">
                    <span className={`font-medium ${rule.click_rate >= 5 ? 'text-green-600' : 'text-gray-600'}`}>
                      {rule.click_rate}%
                    </span>
                  </td>
                  <td className="text-right py-3 px-4">
                    <span className="font-medium text-gray-900">
                      ${rule.revenue.toLocaleString()}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Trigger Comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow-sm border p-6">
          <h2 className="text-xl font-semibold mb-4">Performance by Trigger Type</h2>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={triggerComparison}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="trigger_type" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="workflows_started" fill="#3b82f6" name="Workflows" />
              <Bar dataKey="emails_sent" fill="#10b981" name="Emails" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-lg shadow-sm border p-6">
          <h2 className="text-xl font-semibold mb-4">Completion Rates</h2>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={triggerComparison}
                dataKey="completion_rate"
                nameKey="trigger_type"
                cx="50%"
                cy="50%"
                outerRadius={100}
                label
              >
                {triggerComparison.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

// Stat Card Component
const StatCard = ({ icon, title, value, subtitle, color }) => {
  const colorClasses = {
    blue: 'bg-blue-50 border-blue-200',
    green: 'bg-green-50 border-green-200',
    purple: 'bg-purple-50 border-purple-200',
    orange: 'bg-orange-50 border-orange-200'
  };

  return (
    <div className={`${colorClasses[color]} border rounded-lg p-6`}>
      <div className="flex items-center justify-between mb-2">
        <div className="p-2 bg-white rounded-lg">{icon}</div>
      </div>
      <h3 className="text-gray-600 text-sm font-medium mb-1">{title}</h3>
      <p className="text-3xl font-bold text-gray-900 mb-1">{value.toLocaleString()}</p>
      <p className="text-sm text-gray-600">{subtitle}</p>
    </div>
  );
};

export default AutomationAnalytics;