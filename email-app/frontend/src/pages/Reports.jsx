import { useState, useEffect } from 'react';
import API from '../api';
import { Download, FileText } from 'lucide-react';

export default function Reports() {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [exportFormat, setExportFormat] = useState('csv');
  const [selectedCampaign, setSelectedCampaign] = useState(null);

  useEffect(() => {
    fetchCampaigns();
  }, []);

  const fetchCampaigns = async () => {
    try {
      setLoading(true);
      const response = await API.get('/campaigns');
      setCampaigns(response.data.campaigns || []);
    } catch (error) {
      console.error('Error fetching campaigns:', error);
    } finally {
      setLoading(false);
    }
  };

  const exportReport = async (campaignId, format) => {
    try {
      const response = await API.get(`/analytics/campaign/${campaignId}/export?format=${format}`, {
        responseType: format === 'pdf' ? 'blob' : 'text',
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `report_${campaignId}.${format}`);
      document.body.appendChild(link);
      link.click();
      link.parentNode.removeChild(link);
    } catch (error) {
      console.error('Error exporting report:', error);
      alert('Failed to export report');
    }
  };

  const downloadBatchReport = async () => {
    try {
      const response = await API.get('/analytics/campaigns/export?format=csv', {
        responseType: 'text',
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `all-campaigns-report.csv`);
      document.body.appendChild(link);
      link.click();
      link.parentNode.removeChild(link);
    } catch (error) {
      console.error('Error exporting batch report:', error);
      alert('Failed to export batch report');
    }
  };

  if (loading) {
    return (
      <div className="animate-pulse space-y-6">
        <div className="h-8 bg-gray-200 rounded w-1/4"></div>
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-20 bg-gray-200 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:justify-between lg:items-center space-y-4 lg:space-y-0">
        <h1 className="text-2xl font-bold text-gray-900">📄 Campaign Reports</h1>
        <button
          onClick={downloadBatchReport}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
          data-testid="button-export-all"
        >
          <Download size={18} />
          Export All Reports (CSV)
        </button>
      </div>

      {/* Export Format Selector */}
      <div className="bg-white p-6 rounded-lg shadow border">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Default Export Format
        </label>
        <select
          value={exportFormat}
          onChange={(e) => setExportFormat(e.target.value)}
          className="px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
          data-testid="select-export-format"
        >
          <option value="csv">CSV (Excel/Sheets)</option>
          <option value="json">JSON (Data)</option>
          <option value="pdf">PDF (Formatted)</option>
        </select>
      </div>

      {/* Campaign Reports List */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-gray-800">Campaign Reports</h2>
        {campaigns.length === 0 ? (
          <p className="text-gray-500">No campaigns available for reporting.</p>
        ) : (
          <div className="grid gap-4">
            {campaigns.map((campaign) => (
              <div
                key={campaign._id}
                className="bg-white p-6 rounded-lg shadow border hover:shadow-lg transition"
                data-testid={`card-campaign-${campaign._id}`}
              >
                <div className="flex flex-col md:flex-row md:justify-between md:items-start gap-4">
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-gray-900">{campaign.name}</h3>
                    <p className="text-sm text-gray-600 mt-1">
                      Status: <span className="font-medium capitalize">{campaign.status}</span>
                    </p>
                    <p className="text-sm text-gray-600">
                      Recipients: <span className="font-medium">{campaign.recipient_count || 0}</span>
                    </p>
                    {campaign.stats && (
                      <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                        <div>
                          <p className="text-gray-500">Sent</p>
                          <p className="font-bold text-gray-900">{campaign.stats.sent || 0}</p>
                        </div>
                        <div>
                          <p className="text-gray-500">Opens</p>
                          <p className="font-bold text-green-600">{campaign.stats.opens || 0}</p>
                        </div>
                        <div>
                          <p className="text-gray-500">Clicks</p>
                          <p className="font-bold text-blue-600">{campaign.stats.clicks || 0}</p>
                        </div>
                        <div>
                          <p className="text-gray-500">Bounces</p>
                          <p className="font-bold text-red-600">{campaign.stats.bounces || 0}</p>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex flex-col gap-2">
                    <button
                      onClick={() => exportReport(campaign._id, 'csv')}
                      className="flex items-center gap-2 px-4 py-2 bg-green-100 text-green-700 rounded-lg hover:bg-green-200 transition"
                      data-testid={`button-export-csv-${campaign._id}`}
                    >
                      <FileText size={16} />
                      CSV
                    </button>
                    <button
                      onClick={() => exportReport(campaign._id, 'json')}
                      className="flex items-center gap-2 px-4 py-2 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 transition"
                      data-testid={`button-export-json-${campaign._id}`}
                    >
                      <FileText size={16} />
                      JSON
                    </button>
                    <button
                      onClick={() => exportReport(campaign._id, 'pdf')}
                      className="flex items-center gap-2 px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition"
                      data-testid={`button-export-pdf-${campaign._id}`}
                    >
                      <FileText size={16} />
                      PDF
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
