// src/pages/AutomationAnalytics.jsx - Enhanced Version
import React, { useState, useEffect } from 'react';
import {
  BarChart3, TrendingUp, TrendingDown, Mail, Users,
  ArrowLeft, Download, RefreshCw, Clock, Target,
  CheckCircle, XCircle, MousePointerClick, Eye
} from 'lucide-react';
import { useParams, useNavigate } from 'react-router-dom';
import API from '../api';

const AutomationAnalytics = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [analytics, setAnalytics] = useState(null);
  const [automation, setAutomation] = useState(null);
  const [dateRange, setDateRange] = useState('30d');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (id) {
      fetchData();
    }
  }, [id, dateRange]);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [analyticsData, automationData] = await Promise.all([
        API.get(`/automation/rules/${id}/analytics?range=${dateRange}`),
        API.get(`/automation/rules/${id}`)
      ]);

      setAnalytics(analyticsData);
      setAutomation(automationData?.data || automationData);

    } catch (error) {
      console.error('Failed to fetch analytics:', error);
      setError('Failed to load analytics data');
    } finally {
      setLoading(false);
    }
  };

  const exportData = () => {
    if (!analytics) return;

    const csvContent = [
      ['Automation Analytics Report'],
      ['Automation:', automation?.name || 'Unknown'],
      ['Period:', dateRange],
      ['Generated:', new Date().toLocaleString()],
      [],
      ['Metric', 'Value'],
      ['Total Sent', analytics.total_sent],
      ['Total Delivered', analytics.total_delivered],
      ['Total Opened', analytics.total_opened],
      ['Total Clicked', analytics.total_clicked],
      ['Open Rate', `${analytics.open_rate}%`],
      ['Click Rate', `${analytics.click_rate}%`],
      ['Bounce Rate', `${analytics.bounce_rate}%`],
      [],
      ['Email Performance'],
      ['Step', 'Subject', 'Sent', 'Opens', 'Clicks', 'Open Rate', 'Click Rate'],
      ...analytics.email_performance.map((email, idx) => [
        idx + 1,
        email.subject || `Email ${idx + 1}`,
        email.sent,
        email.opened,
        email.clicked,
        `${email.open_rate}%`,
        `${email.click_rate}%`
      ])
    ].map(row => row.join(',')).join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `automation-analytics-${id}-${dateRange}.csv`;
    a.click();
  };

  const getPerformanceIndicator = (rate, type = 'open') => {
    const benchmarks = {
      open: { good: 25, average: 15 },
      click: { good: 3.5, average: 2 }
    };

    const benchmark = benchmarks[type];
    if (rate >= benchmark.good) return { color: 'green', text: 'Excellent', icon: TrendingUp };
    if (rate >= benchmark.average) return { color: 'yellow', text: 'Good', icon: TrendingUp };
    return { color: 'red', text: 'Needs Improvement', icon: TrendingDown };
  };

  if (loading) {
    return (
      <div className="flex flex-col justify-center items-center p-8 min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4"></div>
        <span className="text-gray-600">Loading analytics...</span>
      </div>
    );
  }

  if (error || !analytics) {
    return (
      <div className="p-8 max-w-4xl mx-auto">
        <div className="bg-red-50 border border-red-200 text-red-700 p-6 rounded-lg text-center">
          <XCircle className="mx-auto mb-3" size={48} />
          <p className="text-lg font-medium">{error || 'No analytics data available'}</p>
          <div className="flex gap-3 justify-center mt-4">
            <button
              onClick={() => navigate('/automation')}
              className="bg-red-100 hover:bg-red-200 px-4 py-2 rounded-lg"
            >
              Go Back
            </button>
            <button
              onClick={fetchData}
              className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  const openPerf = getPerformanceIndicator(analytics.open_rate, 'open');
  const clickPerf = getPerformanceIndicator(analytics.click_rate, 'click');

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/automation')}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft size={24} />
          </button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Automation Analytics</h1>
            {automation && (
              <p className="text-gray-600 mt-1">{automation.name}</p>
            )}
          </div>
        </div>

        <div className="flex gap-3">
          <select
            value={dateRange}
            onChange={(e) => setDateRange(e.target.value)}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
          </select>

          <button
            onClick={fetchData}
            className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            title="Refresh data"
          >
            <RefreshCw size={20} />
          </button>

          <button
            onClick={exportData}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
          >
            <Download size={18} />
            Export
          </button>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-blue-100 rounded-lg">
              <Mail className="text-blue-600" size={24} />
            </div>
            <div className="flex-1">
              <p className="text-gray-600 text-sm">Total Sent</p>
              <p className="text-2xl font-bold">{analytics.total_sent?.toLocaleString() || 0}</p>
              <p className="text-xs text-gray-500 mt-1">
                {analytics.total_delivered?.toLocaleString() || 0} delivered
              </p>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
          <div className="flex items-center gap-3">
            <div className={`p-3 bg-${openPerf.color}-100 rounded-lg`}>
              <Eye className={`text-${openPerf.color}-600`} size={24} />
            </div>
            <div className="flex-1">
              <p className="text-gray-600 text-sm">Open Rate</p>
              <p className="text-2xl font-bold">{analytics.open_rate?.toFixed(1) || 0}%</p>
              <div className="flex items-center gap-1 mt-1">
                <openPerf.icon size={12} className={`text-${openPerf.color}-600`} />
                <p className={`text-xs text-${openPerf.color}-600 font-medium`}>
                  {openPerf.text}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
          <div className="flex items-center gap-3">
            <div className={`p-3 bg-${clickPerf.color}-100 rounded-lg`}>
              <MousePointerClick className={`text-${clickPerf.color}-600`} size={24} />
            </div>
            <div className="flex-1">
              <p className="text-gray-600 text-sm">Click Rate</p>
              <p className="text-2xl font-bold">{analytics.click_rate?.toFixed(1) || 0}%</p>
              <div className="flex items-center gap-1 mt-1">
                <clickPerf.icon size={12} className={`text-${clickPerf.color}-600`} />
                <p className={`text-xs text-${clickPerf.color}-600 font-medium`}>
                  {clickPerf.text}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-purple-100 rounded-lg">
              <Users className="text-purple-600" size={24} />
            </div>
            <div className="flex-1">
              <p className="text-gray-600 text-sm">Active Subscribers</p>
              <p className="text-2xl font-bold">{analytics.active_subscribers?.toLocaleString() || 0}</p>
              <p className="text-xs text-gray-500 mt-1">In target audience</p>
            </div>
          </div>
        </div>
      </div>

      {/* Performance Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Engagement Stats */}
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Target className="text-purple-600" size={20} />
            Engagement Breakdown
          </h3>

          <div className="space-y-4">
            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm text-gray-600">Opens</span>
                <span className="text-sm font-medium">{analytics.total_opened?.toLocaleString() || 0}</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-green-500 h-2 rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(analytics.open_rate || 0, 100)}%` }}
                ></div>
              </div>
            </div>

            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm text-gray-600">Clicks</span>
                <span className="text-sm font-medium">{analytics.total_clicked?.toLocaleString() || 0}</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-blue-500 h-2 rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(analytics.click_rate || 0, 100)}%` }}
                ></div>
              </div>
            </div>

            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm text-gray-600">Bounces</span>
                <span className="text-sm font-medium">{analytics.total_bounced?.toLocaleString() || 0}</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-red-500 h-2 rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(analytics.bounce_rate || 0, 100)}%` }}
                ></div>
              </div>
            </div>

            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm text-gray-600">Unsubscribes</span>
                <span className="text-sm font-medium">{analytics.total_unsubscribed?.toLocaleString() || 0}</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-orange-500 h-2 rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(analytics.unsubscribe_rate || 0, 100)}%` }}
                ></div>
              </div>
            </div>
          </div>
        </div>

        {/* Quick Stats */}
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <BarChart3 className="text-blue-600" size={20} />
            Quick Stats
          </h3>

          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 bg-blue-50 rounded-lg">
              <p className="text-sm text-gray-600 mb-1">Delivery Rate</p>
              <p className="text-2xl font-bold text-blue-600">
                {((analytics.total_delivered / analytics.total_sent * 100) || 0).toFixed(1)}%
              </p>
            </div>

            <div className="p-4 bg-green-50 rounded-lg">
              <p className="text-sm text-gray-600 mb-1">Click-to-Open</p>
              <p className="text-2xl font-bold text-green-600">
                {analytics.total_opened > 0
                  ? ((analytics.total_clicked / analytics.total_opened * 100) || 0).toFixed(1)
                  : 0}%
              </p>
            </div>

            <div className="p-4 bg-purple-50 rounded-lg">
              <p className="text-sm text-gray-600 mb-1">Avg per Step</p>
              <p className="text-2xl font-bold text-purple-600">
                {analytics.email_performance?.length > 0
                  ? Math.round(analytics.total_sent / analytics.email_performance.length).toLocaleString()
                  : 0}
              </p>
            </div>

            <div className="p-4 bg-orange-50 rounded-lg">
              <p className="text-sm text-gray-600 mb-1">Total Steps</p>
              <p className="text-2xl font-bold text-orange-600">
                {analytics.email_performance?.length || 0}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Email Performance Table */}
      <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Mail className="text-green-600" size={20} />
            Email Sequence Performance
          </h2>
          <p className="text-sm text-gray-600 mt-1">
            Step-by-step breakdown of your automation emails
          </p>
        </div>

        {!analytics.email_performance || analytics.email_performance.length === 0 ? (
          <div className="p-12 text-center">
            <Clock size={48} className="mx-auto text-gray-300 mb-3" />
            <p className="text-gray-600">No performance data available yet</p>
            <p className="text-sm text-gray-500 mt-1">Data will appear once emails start being sent</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Step
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Email Subject
                  </th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Sent
                  </th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Opened
                  </th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Clicked
                  </th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Open Rate
                  </th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Click Rate
                  </th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Performance
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {analytics.email_performance.map((email, index) => {
                  const stepPerf = getPerformanceIndicator(email.open_rate, 'open');

                  return (
                    <tr key={index} className="hover:bg-gray-50 transition-colors">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          <div className="w-8 h-8 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center font-bold text-sm">
                            {email.step_order || index + 1}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="font-medium text-gray-900 max-w-md truncate">
                          {email.subject || `Email ${index + 1}`}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className="text-sm font-medium text-gray-900">
                          {email.sent?.toLocaleString() || 0}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className="text-sm text-gray-900">
                          {email.opened?.toLocaleString() || 0}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className="text-sm text-gray-900">
                          {email.clicked?.toLocaleString() || 0}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <div className="flex items-center justify-center gap-2">
                          <span className="text-sm font-medium text-gray-900">
                            {email.open_rate?.toFixed(1) || 0}%
                          </span>
                          <div className="w-16 bg-gray-200 rounded-full h-1.5">
                            <div
                              className={`bg-green-500 h-1.5 rounded-full`}
                              style={{ width: `${Math.min(email.open_rate || 0, 100)}%` }}
                            ></div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <div className="flex items-center justify-center gap-2">
                          <span className="text-sm font-medium text-gray-900">
                            {email.click_rate?.toFixed(1) || 0}%
                          </span>
                          <div className="w-16 bg-gray-200 rounded-full h-1.5">
                            <div
                              className={`bg-blue-500 h-1.5 rounded-full`}
                              style={{ width: `${Math.min(email.click_rate || 0, 100)}%` }}
                            ></div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className={`px-3 py-1 text-xs rounded-full font-medium bg-${stepPerf.color}-100 text-${stepPerf.color}-800 inline-flex items-center gap-1`}>
                          <stepPerf.icon size={12} />
                          {stepPerf.text}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Insights & Recommendations */}
      <div className="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Performance Insights */}
        <div className="bg-gradient-to-br from-blue-50 to-purple-50 border border-blue-200 rounded-lg p-6">
          <h3 className="font-semibold text-lg mb-3 flex items-center gap-2">
            <CheckCircle className="text-blue-600" size={20} />
            Performance Insights
          </h3>
          <ul className="space-y-2 text-sm">
            {analytics.open_rate > 25 && (
              <li className="flex items-start gap-2">
                <span className="text-green-600">✓</span>
                <span>Excellent open rate! Your subject lines are working well.</span>
              </li>
            )}
            {analytics.click_rate > 3 && (
              <li className="flex items-start gap-2">
                <span className="text-green-600">✓</span>
                <span>Strong click-through rate indicates engaging content.</span>
              </li>
            )}
            {analytics.bounce_rate < 2 && (
              <li className="flex items-start gap-2">
                <span className="text-green-600">✓</span>
                <span>Low bounce rate shows good list hygiene.</span>
              </li>
            )}
            {analytics.email_performance?.length > 3 && (
              <li className="flex items-start gap-2">
                <span className="text-blue-600">ℹ</span>
                <span>Multi-step sequence is nurturing subscribers effectively.</span>
              </li>
            )}
          </ul>
        </div>

        {/* Recommendations */}
        <div className="bg-gradient-to-br from-orange-50 to-yellow-50 border border-orange-200 rounded-lg p-6">
          <h3 className="font-semibold text-lg mb-3 flex items-center gap-2">
            <TrendingUp className="text-orange-600" size={20} />
            Recommendations
          </h3>
          <ul className="space-y-2 text-sm">
            {analytics.open_rate < 15 && (
              <li className="flex items-start gap-2">
                <span className="text-orange-600">⚠</span>
                <span>Test different subject lines to improve open rates.</span>
              </li>
            )}
            {analytics.click_rate < 2 && (
              <li className="flex items-start gap-2">
                <span className="text-orange-600">⚠</span>
                <span>Consider making CTAs more prominent in your emails.</span>
              </li>
            )}
            {analytics.bounce_rate > 5 && (
              <li className="flex items-start gap-2">
                <span className="text-red-600">✕</span>
                <span>High bounce rate - review and clean your email list.</span>
              </li>
            )}
            <li className="flex items-start gap-2">
              <span className="text-blue-600">💡</span>
              <span>A/B test email timing for better engagement.</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default AutomationAnalytics;