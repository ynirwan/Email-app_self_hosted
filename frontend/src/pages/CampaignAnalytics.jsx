import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import API from '../api';
import { useNavigate } from 'react-router-dom';




export default function CampaignAnalytics() {
  const { campaignId } = useParams();
  const navigate = useNavigate();	
  const [analyticsData, setAnalyticsData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchCampaignAnalytics();
  }, [campaignId]);

  const fetchCampaignAnalytics = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await API.get(`/analytics/campaigns/${campaignId}`);
      setAnalyticsData(response.data);
    } catch (error) {
      console.error('Error fetching campaign analytics:', error);
      setError(error.response?.data?.detail || 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <LoadingSkeleton />;
  }

  if (error) {
    return <ErrorState error={error} onRetry={fetchCampaignAnalytics} />;
  }

  const { campaign, analytics, recent_events, top_links } = analyticsData || {};

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Clean Header */}
        <div className="bg-white rounded-lg shadow-sm border mb-6">
          <div className="px-6 py-5">
            <div className="flex flex-col lg:flex-row lg:justify-between lg:items-center space-y-4 lg:space-y-0">
              <div>
                <div className="flex items-center space-x-3 mb-2">
                  <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                    <span className="text-white text-xl">📊</span>
                  </div>
                  <div>
                    <h1 className="text-2xl font-bold text-gray-900">Campaign Analytics</h1>
                    <div className="flex items-center space-x-3 mt-1">
                      <p className="text-gray-600">{campaign?.title}</p>
                      <CampaignStatusBadge status={campaign?.status} />
                    </div>
                  </div>
                </div>
              </div>
              <div className="flex space-x-3">
                <button 
                  onClick={fetchCampaignAnalytics}
                  className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors flex items-center space-x-2"
                >
                  <span>🔄</span>
                  <span>Refresh</span>
                </button>
                    <button
                        onClick={() => navigate(-1)}
                            className="px-4 py-2 bg-blue-600 rounded hover:bg-blue-300"
                    >        

                  <span>←</span>
                  <span>Back</span>
	      </button>
              </div>
            </div>
          </div>
        </div>

        {/* Campaign Progress - Simplified */}
        <div className="bg-white rounded-lg shadow-sm border mb-6">
          <div className="px-6 py-5 border-b border-gray-200">
            <div className="flex items-center space-x-2">
              <span className="text-lg">📤</span>
              <h2 className="text-lg font-semibold text-gray-900">Campaign Progress</h2>
            </div>
          </div>
          
          <div className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
              <ProgressCard
                title="Target Subscribers"
                value={campaign?.target_list_count || 0}
                subtitle="Total to send to"
                icon="🎯"
                color="bg-blue-50 text-blue-700 border-blue-200"
              />
              <ProgressCard
                title="Processed"
                value={campaign?.processed_count || 0}
                subtitle="Emails processed"
                icon="⚙️"
                color="bg-green-50 text-green-700 border-green-200"
              />
              <ProgressCard
                title="Sent Successfully"
                value={campaign?.sent_count || 0}
                subtitle="Successfully sent"
                icon="✅"
                color="bg-purple-50 text-purple-700 border-purple-200"
              />
              <ProgressCard
                title="In Queue"
                value={campaign?.queued_count || 0}
                subtitle="Waiting to send"
                icon="⏳"
                color="bg-orange-50 text-orange-700 border-orange-200"
              />
            </div>

            {/* Simple Progress Bar */}
            <div className="mb-4">
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-medium text-gray-700">Progress</span>
                <span className="text-sm text-gray-600">
                  {campaign?.target_list_count > 0 
                    ? `${Math.round((campaign?.sent_count / campaign?.target_list_count) * 100)}%`
                    : '0%'
                  }
                </span>
              </div>
              <div className="bg-gray-200 rounded-full h-2">
                <div 
                  className="bg-blue-600 h-2 rounded-full transition-all duration-500"
                  style={{ 
                    width: `${campaign?.target_list_count > 0 ? (campaign?.sent_count / campaign?.target_list_count) * 100 : 0}%` 
                  }}
                ></div>
              </div>
            </div>

            {/* Simple Timeline */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t border-gray-200">
              <TimelineItem
                label="Started"
                value={campaign?.started_at ? new Date(campaign.started_at).toLocaleString() : 'Not started'}
              />
              <TimelineItem
                label="Last Batch"
                value={campaign?.last_batch_at ? new Date(campaign.last_batch_at).toLocaleString() : 'N/A'}
              />
              <TimelineItem
                label="Completed"
                value={campaign?.completed_at ? new Date(campaign.completed_at).toLocaleString() : 'In progress'}
              />
            </div>
          </div>
        </div>


         {/* Engagement Metrics - Clean */}
<div className="mb-6">
  <div className="flex items-center space-x-2 mb-4">
    <span className="text-lg">📈</span>
    <h2 className="text-lg font-semibold text-gray-900">Engagement Metrics</h2>
  </div>
  
  {/* Positive Metrics */}
  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
    <MetricCard
      title="Total Sent"
      value={analytics?.total_sent || 0}
      subtitle="From campaign data"
      icon="📧"
      color="text-blue-600"
      bgColor="bg-blue-50"
    />
    <MetricCard
      title="Opens"
      value={analytics?.total_opened || 0}
      subtitle={`${analytics?.open_rate || 0}% open rate`}
      icon="👁️"
      color="text-green-600"
      bgColor="bg-green-50"
    />
    <MetricCard
      title="Clicks"
      value={analytics?.total_clicked || 0}
      subtitle={`${analytics?.click_rate || 0}% click rate`}
      icon="👆"
      color="text-purple-600"
      bgColor="bg-purple-50"
    />
    <MetricCard
      title="Delivered"
      value={analytics?.total_delivered || (analytics?.total_sent - analytics?.total_bounced) || 0}
      subtitle={`${analytics?.delivery_rate || 0}% delivery rate`}
      icon="✅"
      color="text-teal-600"
      bgColor="bg-teal-50"
    />
  </div>

  {/* Negative Metrics grouped */}
  <div className="bg-red-50 border border-red-100 rounded-lg p-5">
    <h3 className="text-md font-semibold text-red-800 mb-4 flex items-center space-x-2">
      <span>⚠️</span>
      <span>Issues & Failures</span>
    </h3>
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <MetricCard
        title="Bounces"
        value={analytics?.total_bounced || 0}
        subtitle={`${analytics?.bounce_rate || 0}% bounce rate`}
        icon="⚠️"
        color="text-red-600"
        bgColor="bg-red-100"
      />
      <MetricCard
        title="Unsubscribes"
        value={analytics?.total_unsubscribed || 0}
        subtitle={`${analytics?.unsubscribe_rate || 0}% unsubscribe rate`}
        icon="🚫"
        color="text-orange-600"
        bgColor="bg-orange-100"
      />
      <MetricCard
        title="Spam Reports"
        value={analytics?.total_spam_reports || 0}
        subtitle="Marked as spam"
        icon="🚨"
        color="text-red-700"
        bgColor="bg-red-100"
      />
    </div>
  </div>
</div>

        

        {/* Performance Overview - Clean */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          <TopClickedLinks links={top_links} />
          <RecentActivity events={recent_events} />
        </div>

        {/* Campaign Details - Clean */}
        <CampaignDetails campaign={campaign} />
      </div>
    </div>
  );
}

// Simplified Components
const ProgressCard = ({ title, value, subtitle, icon, color }) => (
  <div className={`${color} border rounded-lg p-4 hover:shadow-sm transition-shadow`}>
    <div className="text-center">
      <div className="text-2xl mb-2">{icon}</div>
      <p className="text-sm font-medium mb-1">{title}</p>
      <p className="text-2xl font-bold mb-1">{value?.toLocaleString()}</p>
      <p className="text-xs opacity-75">{subtitle}</p>
    </div>
  </div>
);

const TimelineItem = ({ label, value }) => (
  <div>
    <p className="text-sm font-medium text-gray-900 mb-1">{label}</p>
    <p className="text-sm text-gray-600">{value}</p>
  </div>
);

const MetricCard = ({ title, value, subtitle, icon, color, bgColor }) => (
  <div className={`bg-white ${bgColor} rounded-lg p-5 shadow-sm border hover:shadow-md transition-shadow`}>
    <div className="text-center">
      <div className="text-2xl mb-3">{icon}</div>
      <p className="text-sm font-medium text-gray-600 mb-2">{title}</p>
      <p className={`text-3xl font-bold ${color} mb-2`}>
        {typeof value === 'number' ? value.toLocaleString() : value}
      </p>
      {subtitle && <p className="text-sm text-gray-500">{subtitle}</p>}
    </div>
  </div>
);

const TopClickedLinks = ({ links }) => (
  <div className="bg-white rounded-lg shadow-sm border">
    <div className="px-6 py-4 border-b border-gray-200">
      <h3 className="text-lg font-semibold text-gray-900 flex items-center space-x-2">
        <span>🔗</span>
        <span>Top Clicked Links</span>
      </h3>
    </div>
    <div className="p-6">
      {links?.length > 0 ? (
        <div className="space-y-3">
          {links.map((link, index) => (
            <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
              <div className="flex items-center space-x-3 flex-1 min-w-0">
                <div className="w-6 h-6 bg-blue-600 text-white rounded-md flex items-center justify-center text-xs font-bold">
                  {index + 1}
                </div>
                <p className="text-sm font-medium text-gray-900 truncate" title={link.url}>
                  {link.url || 'Unknown URL'}
                </p>
              </div>
              <span className="px-3 py-1 bg-blue-100 text-blue-800 text-sm font-medium rounded-full">
                {link.clicks} clicks
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-8">
          <div className="text-4xl text-gray-300 mb-3">🔗</div>
          <p className="text-gray-500 mb-1">No link clicks recorded yet</p>
          <p className="text-sm text-gray-400">Links will appear here once users start clicking</p>
        </div>
      )}
    </div>
  </div>
);

const RecentActivity = ({ events }) => (
  <div className="bg-white rounded-lg shadow-sm border">
    <div className="px-6 py-4 border-b border-gray-200">
      <h3 className="text-lg font-semibold text-gray-900 flex items-center space-x-2">
        <span>📈</span>
        <span>Recent Activity</span>
      </h3>
    </div>
    <div className="p-6">
      {events?.length > 0 ? (
        <div className="space-y-3 max-h-80 overflow-y-auto">
          {events.slice(0, 15).map((event, index) => (
            <div key={index} className="flex items-center space-x-3 p-2 hover:bg-gray-50 rounded-lg transition-colors">
              <EventIcon eventType={event.event_type} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900">
                  <span className="capitalize">{event.event_type}</span>
                  {event.subscriber_email && (
                    <span className="text-gray-500 ml-2">• {event.subscriber_email}</span>
                  )}
                </p>
                <p className="text-xs text-gray-500">
                  {new Date(event.timestamp).toLocaleString()}
                </p>
                {event.url && event.event_type === 'clicked' && (
                  <p className="text-xs text-blue-600 truncate mt-1" title={event.url}>
                    🔗 {event.url}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-8">
          <div className="text-4xl text-gray-300 mb-3">📊</div>
          <p className="text-gray-500 mb-1">No recent activity</p>
          <p className="text-sm text-gray-400">Activity will appear here as subscribers interact</p>
        </div>
      )}
    </div>
  </div>
);

const EventIcon = ({ eventType }) => {
  const iconConfig = {
    opened: { icon: '👁️', bg: 'bg-green-100', color: 'text-green-600' },
    clicked: { icon: '👆', bg: 'bg-purple-100', color: 'text-purple-600' },
    bounced: { icon: '⚠️', bg: 'bg-red-100', color: 'text-red-600' },
    delivered: { icon: '✅', bg: 'bg-green-100', color: 'text-green-600' },
    unsubscribed: { icon: '🚫', bg: 'bg-orange-100', color: 'text-orange-600' },
    spam_report: { icon: '🚨', bg: 'bg-red-100', color: 'text-red-600' }
  };
  
  const config = iconConfig[eventType] || { icon: '📧', bg: 'bg-gray-100', color: 'text-gray-600' };
  
  return (
    <div className={`w-8 h-8 ${config.bg} rounded-lg flex items-center justify-center flex-shrink-0`}>
      <span className={`text-sm ${config.color}`}>{config.icon}</span>
    </div>
  );
};

const CampaignDetails = ({ campaign }) => (
  <div className="bg-white rounded-lg shadow-sm border">
    <div className="px-6 py-4 border-b border-gray-200">
      <div className="flex items-center space-x-2">
        <span className="text-lg">📧</span>
        <h3 className="text-lg font-semibold text-gray-900">Campaign Details</h3>
      </div>
    </div>
    <div className="p-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <DetailItem label="Campaign Title" value={campaign?.title || 'Untitled Campaign'} />
        <DetailItem label="Subject Line" value={campaign?.subject || 'No subject'} />
        <DetailItem label="Sender Name" value={campaign?.sender_name || 'Unknown'} />
        <DetailItem label="Sender Email" value={campaign?.sender_email || 'Unknown'} />
        <DetailItem label="Reply To" value={campaign?.reply_to || campaign?.sender_email || 'N/A'} />
        <DetailItem 
          label="Status" 
          value={<CampaignStatusBadge status={campaign?.status} />} 
        />
        <DetailItem label="Target Lists" value={campaign?.target_lists?.join(', ') || 'None'} />
        <DetailItem label="Target Count" value={campaign?.target_list_count?.toLocaleString() || '0'} />
        <DetailItem label="Successfully Sent" value={campaign?.sent_count?.toLocaleString() || '0'} />
        <DetailItem 
          label="Created" 
          value={campaign?.created_at ? new Date(campaign.created_at).toLocaleString() : 'Unknown'} 
        />
        <DetailItem 
          label="Started" 
          value={campaign?.started_at ? new Date(campaign.started_at).toLocaleString() : 'Not started'} 
        />
        <DetailItem 
          label="Completed" 
          value={campaign?.completed_at ? new Date(campaign.completed_at).toLocaleString() : 'In progress'} 
        />
      </div>
    </div>
  </div>
);

const DetailItem = ({ label, value }) => (
  <div>
    <h4 className="text-sm font-medium text-gray-500 mb-2">{label}</h4>
    <div className="text-gray-900 font-medium">
      {typeof value === 'string' || typeof value === 'number' ? value : value}
    </div>
  </div>
);

// Simple Loading and Error Components
const LoadingSkeleton = () => (
  <div className="min-h-screen bg-gray-50">
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="animate-pulse space-y-6">
        <div className="bg-white rounded-lg shadow-sm h-20"></div>
        <div className="bg-white rounded-lg shadow-sm h-64"></div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="bg-white rounded-lg shadow-sm h-32"></div>
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white rounded-lg shadow-sm h-96"></div>
          <div className="bg-white rounded-lg shadow-sm h-96"></div>
        </div>
      </div>
    </div>
  </div>
);

const ErrorState = ({ error, onRetry }) => (
  <div className="min-h-screen bg-gray-50 flex items-center justify-center">
    <div className="text-center bg-white rounded-lg shadow-sm p-8 max-w-md mx-4">
      <div className="text-red-500 text-4xl mb-4">⚠️</div>
      <h2 className="text-xl font-semibold text-gray-900 mb-2">Something went wrong</h2>
      <p className="text-gray-600 mb-4">{error}</p>
      <button
        onClick={onRetry}
        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
      >
        Try Again
      </button>
    </div>
  </div>
);

const CampaignStatusBadge = ({ status }) => {
  const statusConfig = {
    sent: { bg: 'bg-green-100', text: 'text-green-800', label: '✅ Sent' },
    draft: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: '📝 Draft' },
    sending: { bg: 'bg-blue-100', text: 'text-blue-800', label: '📤 Sending' },
    failed: { bg: 'bg-red-100', text: 'text-red-800', label: '❌ Failed' }
  };
  
  const config = statusConfig[status] || statusConfig.draft;
  
  return (
    <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${config.bg} ${config.text}`}>
      {config.label}
    </span>
  );
};

