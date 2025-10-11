import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import API from '../api';

export default function Analytics() {
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState(30);

  useEffect(() => {
    fetchDashboardData();
  }, [dateRange]);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      const response = await API.get(`/analytics/dashboard?days=${dateRange}`);
      setDashboardData(response.data);
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="animate-pulse space-y-6">
        <div className="h-8 bg-gray-200 rounded w-1/4"></div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-32 bg-gray-200 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  const { summary, campaigns } = dashboardData || {};

  // Filter out draft and failed campaigns
  const validCampaigns = (campaigns || []).filter(
    (c) => c.status !== 'draft' && c.status !== 'failed'
  );

  // Adjust total campaigns in summary to match filtered data
  const adjustedSummary = {
    ...summary,
    total_campaigns: validCampaigns.length,
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:justify-between lg:items-center space-y-4 lg:space-y-0">
        <h1 className="text-2xl font-bold text-gray-900">📊 Analytics Dashboard</h1>

        <div className="flex gap-4 items-center">
          <select
            value={dateRange}
            onChange={(e) => setDateRange(Number(e.target.value))}
            className="px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last year</option>
          </select>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-white p-6 rounded-lg shadow border">
          <p className="text-sm font-medium text-gray-600">Total Campaigns</p>
          <p className="text-3xl font-bold text-gray-900">
            {adjustedSummary?.total_campaigns || 0}
          </p>
        </div>

        <div className="bg-white p-6 rounded-lg shadow border">
          <p className="text-sm font-medium text-gray-600">Emails Sent</p>
          <p className="text-3xl font-bold text-gray-900">
            {adjustedSummary?.total_emails_sent?.toLocaleString() || 0}
          </p>
        </div>

        <div className="bg-white p-6 rounded-lg shadow border">
          <p className="text-sm font-medium text-gray-600">Average Open Rate</p>
          <p className="text-3xl font-bold text-green-600">
            {adjustedSummary?.average_open_rate || 0}%
          </p>
        </div>

        <div className="bg-white p-6 rounded-lg shadow border">
          <p className="text-sm font-medium text-gray-600">Average Click Rate</p>
          <p className="text-3xl font-bold text-purple-600">
            {adjustedSummary?.average_click_rate || 0}%
          </p>
        </div>
      </div>

      {/* Campaign Performance Table */}
      <div className="bg-white rounded-lg shadow border">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">Campaign Performance</h2>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Campaign</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Sent</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Opens</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Clicks</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Open Rate</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Click Rate</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {validCampaigns.length > 0 ? (
                validCampaigns.map((campaign) => (
                  <tr key={campaign._id} className="hover:bg-gray-50">
                    <td className="px-6 py-4">
                      <div>
                        <p className="text-sm font-medium text-gray-900">{campaign.title}</p>
                        <p className="text-sm text-gray-500">{campaign.subject}</p>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {campaign.analytics?.total_sent?.toLocaleString() || 0}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {campaign.analytics?.total_opened?.toLocaleString() || 0}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {campaign.analytics?.total_clicked?.toLocaleString() || 0}
                    </td>
                    <td className="px-6 py-4">
                      {campaign.analytics?.open_rate?.toFixed(1) || 0}%
                    </td>
                    <td className="px-6 py-4">
                      {campaign.analytics?.click_rate?.toFixed(1) || 0}%
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <Link
                        to={`/analytics/campaign/${campaign._id}`}
                        className="text-blue-600 hover:text-blue-800 font-medium"
                      >
                        View Details →
                      </Link>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="px-6 py-8 text-center text-gray-500">
                    <div className="flex flex-col items-center space-y-3">
                      <span className="text-4xl">📊</span>
                      <p className="text-lg font-medium">No campaigns found</p>
                      <p className="text-sm">Create your first campaign to see analytics here</p>
                      <Link
                        to="/campaigns/create"
                        className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                      >
                        Create Campaign
                      </Link>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

