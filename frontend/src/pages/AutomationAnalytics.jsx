// src/pages/AutomationAnalytics.jsx
import React, { useState, useEffect } from 'react';
import { BarChart3, TrendingUp, Mail, Users } from 'lucide-react';
import { useParams } from 'react-router-dom';
import API from '../api';

const AutomationAnalytics = () => {
  const { id } = useParams();
  const [analytics, setAnalytics] = useState(null);
  const [dateRange, setDateRange] = useState('30d');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (id) {
      fetchAnalytics();
    }
  }, [id, dateRange]);

  const fetchAnalytics = async () => {
    try {
      setLoading(true);
      const data = await API.get(`/automation/rules/${id}/analytics?range=${dateRange}`);
      setAnalytics(data);
    } catch (error) {
      console.error('Failed to fetch analytics:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="p-8 text-center">Loading analytics...</div>;
  if (!analytics) return <div className="p-8 text-center">No analytics data available</div>;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Automation Analytics</h1>
        <select
          value={dateRange}
          onChange={(e) => setDateRange(e.target.value)}
          className="p-2 border border-gray-300 rounded-lg"
        >
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
          <option value="90d">Last 90 days</option>
        </select>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center gap-3">
            <Mail className="text-blue-500" size={24} />
            <div>
              <p className="text-gray-600 text-sm">Total Emails Sent</p>
              <p className="text-2xl font-bold">{analytics.total_sent?.toLocaleString()}</p>
            </div>
          </div>
        </div>
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center gap-3">
            <TrendingUp className="text-green-500" size={24} />
            <div>
              <p className="text-gray-600 text-sm">Open Rate</p>
              <p className="text-2xl font-bold">{analytics.open_rate?.toFixed(1)}%</p>
            </div>
          </div>
        </div>
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center gap-3">
            <BarChart3 className="text-purple-500" size={24} />
            <div>
              <p className="text-gray-600 text-sm">Click Rate</p>
              <p className="text-2xl font-bold">{analytics.click_rate?.toFixed(1)}%</p>
            </div>
          </div>
        </div>
        <div className="bg-white p-6 rounded-lg shadow-sm border">
          <div className="flex items-center gap-3">
            <Users className="text-orange-500" size={24} />
            <div>
              <p className="text-gray-600 text-sm">Active Subscribers</p>
              <p className="text-2xl font-bold">{analytics.active_subscribers?.toLocaleString()}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Email Performance Table */}
      <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold">Email Performance</h2>
        </div>
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Sent</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Opens</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Clicks</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Open Rate</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Click Rate</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {analytics.email_performance?.map((email, index) => (
              <tr key={index} className="hover:bg-gray-50">
                <td className="px-6 py-4 font-medium">{email.subject || `Email ${index + 1}`}</td>
                <td className="px-6 py-4">{email.sent?.toLocaleString()}</td>
                <td className="px-6 py-4">{email.opens?.toLocaleString()}</td>
                <td className="px-6 py-4">{email.clicks?.toLocaleString()}</td>
                <td className="px-6 py-4">{email.open_rate?.toFixed(1)}%</td>
                <td className="px-6 py-4">{email.click_rate?.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ✅ Default export
export default AutomationAnalytics;

