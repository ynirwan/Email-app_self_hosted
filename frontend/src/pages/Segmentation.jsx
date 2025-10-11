import { useEffect, useState } from 'react';
import API from '../api';

export default function Segmentation() {
  const [segments, setSegments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [previewData, setPreviewData] = useState([]);
  const [selectedSegment, setSelectedSegment] = useState(null);
  const [lists, setLists] = useState([]);

  // Enhanced segment form with 8 segmentation types
  const [segmentForm, setSegmentForm] = useState({
    name: '',
    description: '',
    criteria: {
      status: [],                    // 📊 Subscriber Status
      lists: [],                     // 📋 Lists
      dateRange: null,               // 📅 Subscription Date
      profileCompleteness: {},       // 👤 Profile Completeness
      geographic: {                  // 🌍 Geographic
        country: '',
        city: ''
      },
      engagement: [],                // 📈 Engagement Level
      emailDomain: [],               // 📧 Email Domain
      industry: '',                  // 🏷️ Custom Fields - Industry
      companySize: '',               // 🏷️ Custom Fields - Company Size
      customFields: {}               // 🏷️ Additional Custom Fields
    }
  });

  useEffect(() => {
    fetchSegments();
    fetchLists();
  }, []);

  const fetchSegments = async () => {
    try {
      setLoading(true);
      const response = await API.get('/segments');
      console.log('Segments API Response:', response.data);
      
      let segmentsData = [];
      if (response.data) {
        if (Array.isArray(response.data)) {
          segmentsData = response.data;
        } else if (response.data.segments && Array.isArray(response.data.segments)) {
          segmentsData = response.data.segments;
        }
      }
      setSegments(segmentsData);
    } catch (error) {
      console.error('Failed to fetch segments:', error);
      setSegments([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchLists = async () => {
    try {
      const response = await API.get('/subscribers/lists');
      console.log('Lists API Response:', response.data);
      
      let listsData = [];
      if (Array.isArray(response.data)) {
        listsData = response.data;
      } else if (response.data && Array.isArray(response.data.lists)) {
        listsData = response.data.lists;
      }
      setLists(listsData);
    } catch (error) {
      console.error('Failed to fetch lists:', error);
      setLists([]);
    }
  };

  const handleDeleteSegment = async (segmentId, segmentName) => {
    if (!window.confirm(`Are you sure you want to delete segment "${segmentName}"?`)) return;

    try {
      await API.delete(`/segments/${segmentId}`);
      setSegments(segments.filter(s => s._id !== segmentId));
      alert('Segment deleted successfully ✅');
    } catch (error) {
      console.error('Delete failed:', error);
      alert('Failed to delete segment');
    }
  };

  const handlePreviewSegment = async (segment) => {
    try {
      setLoading(true);
      const response = await API.post('/segments/preview', {
        criteria: segment.criteria || segment.query
      });
      setPreviewData(response.data.subscribers || []);
      setSelectedSegment(segment);
      setShowPreviewModal(true);
    } catch (error) {
      console.error('Preview failed:', error);
      alert('Failed to load segment preview');
    } finally {
      setLoading(false);
    }
  };

  const handleEditSegment = (segment) => {
    setSelectedSegment(segment);
    setSegmentForm({
      name: segment.name,
      description: segment.description,
      criteria: segment.criteria || {
        status: [],
        lists: [],
        dateRange: null,
        profileCompleteness: {},
        geographic: { country: '', city: '' },
        engagement: [],
        emailDomain: [],
        industry: '',
        companySize: '',
        customFields: {}
      }
    });
    setShowCreateModal(true);
  };

  // Reset form helper
  const resetForm = () => {
    setSegmentForm({
      name: '',
      description: '',
      criteria: {
        status: [],
        lists: [],
        dateRange: null,
        profileCompleteness: {},
        geographic: { country: '', city: '' },
        engagement: [],
        emailDomain: [],
        industry: '',
        companySize: '',
        customFields: {}
      }
    });
  };

  if (loading && segments.length === 0) {
    return (
      <div className="max-w-7xl mx-auto mt-10 p-4">
        <div className="text-center">
          <div className="text-4xl mb-4">🔄</div>
          <p className="text-lg">Loading segments...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto mt-10">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold">🎯 Advanced Segmentation</h2>
          <p className="text-gray-600">Create targeted segments with 8 different criteria types</p>
        </div>
        <button
          onClick={() => {
            setSelectedSegment(null);
            resetForm();
            setShowCreateModal(true);
          }}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 flex items-center gap-2"
        >
          <span>➕</span> Create Segment
        </button>
      </div>

      {/* Enhanced Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
        <div className="bg-white p-4 rounded-lg shadow">
          <div className="text-2xl font-bold text-blue-600">{segments?.length || 0}</div>
          <div className="text-sm text-gray-600">Total Segments</div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <div className="text-2xl font-bold text-green-600">
            {Array.isArray(segments) ? segments.filter(s => s.is_active).length : 0}
          </div>
          <div className="text-sm text-gray-600">Active Segments</div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <div className="text-2xl font-bold text-orange-600">
            {Array.isArray(segments) ? 
              segments.reduce((sum, s) => sum + (s.subscriber_count || 0), 0).toLocaleString() : 
              0
            }
          </div>
          <div className="text-sm text-gray-600">Total Segmented</div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <div className="text-2xl font-bold text-purple-600">{lists?.length || 0}</div>
          <div className="text-sm text-gray-600">Available Lists</div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <div className="text-2xl font-bold text-indigo-600">8</div>
          <div className="text-sm text-gray-600">Segmentation Types</div>
        </div>
      </div>

      {/* Segments Table */}
      <div className="bg-white shadow rounded-lg">
        <div className="p-4 border-b">
          <h3 className="font-semibold">Your Segments</h3>
        </div>
        
        {!Array.isArray(segments) || segments.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            <div className="text-4xl mb-4">🎯</div>
            <h3 className="text-lg font-semibold mb-2">No segments created yet</h3>
            <p className="mb-4">Create your first segment with our 8 powerful segmentation types.</p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
            >
              Create Your First Segment
            </button>
          </div>
        ) : (
          <>
            <table className="w-full table-auto text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="p-3 text-left">Segment Details</th>
                  <th className="p-3 text-left">Size</th>
                  <th className="p-3 text-left">Criteria Types</th>
                  <th className="p-3 text-left">Status</th>
                  <th className="p-3 text-left">Actions</th>
                </tr>
              </thead>
            </table>
            <EnhancedSegmentTable 
              data={segments} 
              onPreview={handlePreviewSegment}
              onEdit={handleEditSegment}
              onDelete={handleDeleteSegment}
            />
          </>
        )}
      </div>

      {/* Enhanced Create/Edit Modal */}
      <EnhancedSegmentModal
        show={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        segmentForm={segmentForm}
        setSegmentForm={setSegmentForm}
        lists={lists}
        onSave={fetchSegments}
        isEditing={!!selectedSegment}
        segmentId={selectedSegment?._id}
      />

      {/* Preview Modal */}
      <SegmentPreviewModal
        show={showPreviewModal}
        onClose={() => setShowPreviewModal(false)}
        segment={selectedSegment}
        previewData={previewData}
      />
    </div>
  );
}

// Enhanced Segment Table Component
const EnhancedSegmentTable = ({ data, height = 400, onPreview, onEdit, onDelete }) => {
  const [scrollTop, setScrollTop] = useState(0);
  const rowHeight = 60;
  const visibleRows = Math.ceil(height / rowHeight);
  const buffer = 5;

  const start = Math.max(0, Math.floor(scrollTop / rowHeight) - buffer);
  const end = Math.min(data.length, start + visibleRows + buffer * 2);
  const visible = data.slice(start, end);

  // Helper to display criteria types
  const getCriteriaTypes = (criteria) => {
    const types = [];
    if (criteria?.status?.length > 0) types.push('Status');
    if (criteria?.lists?.length > 0) types.push('Lists');
    if (criteria?.dateRange) types.push('Date');
    if (criteria?.profileCompleteness && Object.keys(criteria.profileCompleteness).length > 0) types.push('Profile');
    if (criteria?.geographic && (criteria.geographic.country || criteria.geographic.city)) types.push('Geographic');
    if (criteria?.engagement?.length > 0) types.push('Engagement');
    if (criteria?.emailDomain?.length > 0) types.push('Domain');
    if (criteria?.industry || criteria?.companySize || (criteria?.customFields && Object.keys(criteria.customFields).length > 0)) types.push('Custom');
    return types;
  };

  return (
    <div 
      style={{ height, overflow: "auto" }} 
      onScroll={(e) => setScrollTop(e.target.scrollTop)}
    >
      <div style={{ height: `${data.length * rowHeight}px`, position: "relative" }}>
        <table className="w-full table-auto text-sm absolute top-0 left-0">
          <tbody style={{ transform: `translateY(${start * rowHeight}px)` }}>
            {visible.map((segment, index) => (
              <tr key={segment._id || index} className="border-t hover:bg-gray-50" style={{ height: rowHeight }}>
                <td className="p-3">
                  <div className="flex flex-col">
                    <span className="font-semibold text-blue-800">{segment.name}</span>
                    <span className="text-xs text-gray-600">{segment.description}</span>
                    <span className="text-xs text-gray-500 mt-1">
                      Updated: {segment.updated_at ? new Date(segment.updated_at).toLocaleDateString() : 'N/A'}
                    </span>
                  </div>
                </td>
                <td className="p-3">
                  <div className="flex flex-col">
                    <span className="font-medium text-lg">{segment.subscriber_count?.toLocaleString() || '0'}</span>
                    <span className="text-xs text-gray-500">subscribers</span>
                  </div>
                </td>
                <td className="p-3">
                  <div className="flex flex-wrap gap-1">
                    {getCriteriaTypes(segment.criteria).map(type => (
                      <span key={type} className="bg-purple-100 text-purple-800 px-2 py-1 rounded text-xs">
                        {type}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="p-3">
                  <span className={`px-2 py-1 rounded text-xs ${
                    segment.is_active 
                      ? 'bg-green-100 text-green-800' 
                      : 'bg-gray-100 text-gray-800'
                  }`}>
                    {segment.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td className="p-3">
                  <div className="flex gap-2">
                    <button
                      onClick={() => onPreview(segment)}
                      className="text-blue-600 hover:underline text-sm"
                    >
                      Preview
                    </button>
                    <button
                      onClick={() => onEdit(segment)}
                      className="text-orange-600 hover:underline text-sm"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => onDelete(segment._id, segment.name)}
                      className="text-red-600 hover:underline text-sm"
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// Enhanced Segment Builder Modal with 8 Segmentation Types
const EnhancedSegmentModal = ({ 
  show, 
  onClose, 
  segmentForm, 
  setSegmentForm, 
  lists, 
  onSave, 
  isEditing,
  segmentId 
}) => {
  const [previewCount, setPreviewCount] = useState(0);
  const [previewLoading, setPreviewLoading] = useState(false);

  const handleCriteriaChange = (field, value) => {
    if (field.includes('.')) {
      // Handle nested fields like geographic.country
      const [parent, child] = field.split('.');
      setSegmentForm({
        ...segmentForm,
        criteria: {
          ...segmentForm.criteria,
          [parent]: {
            ...segmentForm.criteria[parent],
            [child]: value
          }
        }
      });
    } else {
      setSegmentForm({
        ...segmentForm,
        criteria: {
          ...segmentForm.criteria,
          [field]: value
        }
      });
    }
  };

  const handlePreviewCount = async () => {
    try {
      setPreviewLoading(true);
      const response = await API.post('/segments/count', {
        criteria: segmentForm.criteria
      });
      setPreviewCount(response.data.count || 0);
    } catch (error) {
      console.error('Preview count failed:', error);
      setPreviewCount(0);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleSave = async () => {
    if (!segmentForm.name.trim()) {
      alert('Segment name is required');
      return;
    }

    try {
      const payload = {
        name: segmentForm.name.trim(),
        description: segmentForm.description.trim(),
        criteria: segmentForm.criteria,
        is_active: true
      };

      if (isEditing) {
        await API.put(`/segments/${segmentId}`, payload);
        alert('Segment updated successfully ✅');
      } else {
        await API.post('/segments', payload);
        alert('Segment created successfully ✅');
      }

      onSave();
      onClose();
    } catch (error) {
      console.error('Save failed:', error);
      alert('Failed to save segment');
    }
  };

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex justify-center items-start pt-5 z-50">
      <div className="bg-white p-6 rounded-lg shadow-xl w-full max-w-6xl max-h-[95vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-6">
          <h3 className="text-xl font-bold">
            {isEditing ? '✏️ Edit Segment' : '➕ Create New Segment'}
            <span className="text-sm font-normal text-gray-600 ml-2">(8 Segmentation Types Available)</span>
          </h3>
          <button onClick={onClose} className="text-gray-600 hover:text-black text-xl">✖</button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Left Column - Basic Info & Preview */}
          <div className="lg:col-span-1">
            <div className="space-y-4">
              <div>
                <label className="block font-semibold mb-2">Segment Name *</label>
                <input
                  type="text"
                  value={segmentForm.name}
                  onChange={(e) => setSegmentForm({...segmentForm, name: e.target.value})}
                  className="w-full border rounded p-2"
                  placeholder="e.g., High Value Tech Users"
                />
              </div>

              <div>
                <label className="block font-semibold mb-2">Description</label>
                <textarea
                  value={segmentForm.description}
                  onChange={(e) => setSegmentForm({...segmentForm, description: e.target.value})}
                  className="w-full border rounded p-2 h-20"
                  placeholder="Describe this segment..."
                />
              </div>

              <div className="bg-blue-50 p-4 rounded">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold">Preview Count</span>
                  <button
                    onClick={handlePreviewCount}
                    disabled={previewLoading}
                    className="text-sm bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700 disabled:opacity-50"
                  >
                    {previewLoading ? '⏳' : '🔄'} Count
                  </button>
                </div>
                <div className="text-2xl font-bold text-blue-600">
                  {previewCount.toLocaleString()} subscribers
                </div>
              </div>
            </div>
          </div>

          {/* Right Column - 8 Segmentation Types */}
          <div className="lg:col-span-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              
              {/* 1. 📊 Subscriber Status */}
              <div>
                <label className="block font-semibold mb-3">📊 Subscriber Status</label>
                <div className="grid grid-cols-2 gap-2">
                  {['active', 'inactive', 'unsubscribed', 'bounced'].map(status => (
                    <label key={status} className="flex items-center bg-gray-50 p-2 rounded hover:bg-gray-100">
                      <input
                        type="checkbox"
                        checked={segmentForm.criteria.status?.includes(status)}
                        onChange={(e) => {
                          const currentStatus = segmentForm.criteria.status || [];
                          const newStatus = e.target.checked
                            ? [...currentStatus, status]
                            : currentStatus.filter(s => s !== status);
                          handleCriteriaChange('status', newStatus);
                        }}
                        className="mr-2"
                      />
                      <span className="capitalize text-sm">{status}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* 2. 📋 Lists */}
              <div>
                <label className="block font-semibold mb-3">📋 Lists</label>
                <div className="border rounded p-3 max-h-32 overflow-y-auto">
                  {lists.length === 0 ? (
                    <div className="text-center py-2">
                      <p className="text-gray-500 text-sm">No lists available</p>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      {lists.map(list => (
                        <label key={list._id} className="flex items-center justify-between hover:bg-gray-50 p-1 rounded">
                          <div className="flex items-center">
                            <input
                              type="checkbox"
                              checked={segmentForm.criteria.lists?.includes(list._id)}
                              onChange={(e) => {
                                const currentLists = segmentForm.criteria.lists || [];
                                const newLists = e.target.checked
                                  ? [...currentLists, list._id]
                                  : currentLists.filter(l => l !== list._id);
                                handleCriteriaChange('lists', newLists);
                              }}
                              className="mr-2"
                            />
                            <span className="text-sm font-medium">{list._id}</span>
                          </div>
                          <span className="text-xs text-gray-500">{list.count || 0}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* 3. 📅 Subscription Date */}
              <div>
                <label className="block font-semibold mb-3">📅 Subscription Date</label>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: 'Last 7 days', value: 7 },
                    { label: 'Last 30 days', value: 30 },
                    { label: 'Last 90 days', value: 90 },
                    { label: 'Last 6 months', value: 180 },
                    { label: 'Last year', value: 365 },
                    { label: 'All time', value: null }
                  ].map(option => (
                    <label key={option.label} className="flex items-center bg-gray-50 p-2 rounded hover:bg-gray-100">
                      <input
                        type="radio"
                        name="dateRange"
                        checked={segmentForm.criteria.dateRange === option.value}
                        onChange={() => handleCriteriaChange('dateRange', option.value)}
                        className="mr-2"
                      />
                      <span className="text-sm">{option.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* 4. 👤 Profile Completeness */}
              <div>
                <label className="block font-semibold mb-3">👤 Profile Completeness</label>
                <div className="space-y-2">
                  {[
                    { field: 'first_name', label: 'Has First Name' },
                    { field: 'last_name', label: 'Has Last Name' },
                  ].map(item => (
                    <label key={item.field} className="flex items-center bg-gray-50 p-2 rounded hover:bg-gray-100">
                      <input
                        type="checkbox"
                        checked={segmentForm.criteria.profileCompleteness?.[item.field] === true}
                        onChange={(e) => {
                          const currentFields = segmentForm.criteria.profileCompleteness || {};
                          const newFields = { ...currentFields };
                          if (e.target.checked) {
                            newFields[item.field] = true;
                          } else {
                            delete newFields[item.field];
                          }
                          handleCriteriaChange('profileCompleteness', newFields);
                        }}
                        className="mr-2"
                      />
                      <span className="text-sm">{item.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* 5. 🌍 Geographic */}
              <div>
                <label className="block font-semibold mb-3">🌍 Geographic</label>
                <div className="space-y-2">
                  <input
                    type="text"
                    placeholder="Country (e.g., United States)"
                    value={segmentForm.criteria.geographic?.country || ''}
                    onChange={(e) => handleCriteriaChange('geographic.country', e.target.value)}
                    className="w-full border rounded p-2 text-sm"
                  />
                  <input
                    type="text"
                    placeholder="City (e.g., New York)"
                    value={segmentForm.criteria.geographic?.city || ''}
                    onChange={(e) => handleCriteriaChange('geographic.city', e.target.value)}
                    className="w-full border rounded p-2 text-sm"
                  />
                </div>
              </div>

              {/* 6. 📈 Engagement Level */}
              <div>
                <label className="block font-semibold mb-3">📈 Engagement Level</label>
                <div className="grid grid-cols-3 gap-2">
                  {['high', 'medium', 'low'].map(level => (
                    <label key={level} className="flex items-center bg-gray-50 p-2 rounded hover:bg-gray-100">
                      <input
                        type="checkbox"
                        checked={segmentForm.criteria.engagement?.includes(level)}
                        onChange={(e) => {
                          const currentEngagement = segmentForm.criteria.engagement || [];
                          const newEngagement = e.target.checked
                            ? [...currentEngagement, level]
                            : currentEngagement.filter(l => l !== level);
                          handleCriteriaChange('engagement', newEngagement);
                        }}
                        className="mr-2"
                      />
                      <span className="capitalize text-sm">{level}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* 7. 📧 Email Domain */}
              <div>
                <label className="block font-semibold mb-3">📧 Email Domain</label>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: 'Gmail', value: 'gmail.com' },
                    { label: 'Yahoo', value: 'yahoo.com' },
                    { label: 'Outlook', value: 'outlook.com' },
                    { label: 'Corporate', value: 'corporate' }
                  ].map(domain => (
                    <label key={domain.value} className="flex items-center bg-gray-50 p-2 rounded hover:bg-gray-100">
                      <input
                        type="checkbox"
                        checked={segmentForm.criteria.emailDomain?.includes(domain.value)}
                        onChange={(e) => {
                          const currentDomains = segmentForm.criteria.emailDomain || [];
                          const newDomains = e.target.checked
                            ? [...currentDomains, domain.value]
                            : currentDomains.filter(d => d !== domain.value);
                          handleCriteriaChange('emailDomain', newDomains);
                        }}
                        className="mr-2"
                      />
                      <span className="text-sm">{domain.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* 8. 🏷️ Custom Fields */}
              <div>
                <label className="block font-semibold mb-3">🏷️ Custom Fields</label>
                <div className="space-y-2">
                  {/* Predefined custom fields */}
                  <input
                    type="text"
                    placeholder="Industry (e.g., Technology)"
                    value={segmentForm.criteria.industry || ''}
                    onChange={(e) => handleCriteriaChange('industry', e.target.value)}
                    className="w-full border rounded p-2 text-sm"
                  />
                  <input
                    type="text"
                    placeholder="Company Size (e.g., 50-200)"
                    value={segmentForm.criteria.companySize || ''}
                    onChange={(e) => handleCriteriaChange('companySize', e.target.value)}
                    className="w-full border rounded p-2 text-sm"
                  />
                  
                  {/* Dynamic custom fields */}
                  {segmentForm.criteria.customFields && Object.keys(segmentForm.criteria.customFields).length > 0 && (
                    <div className="mt-2 space-y-1">
                      {Object.entries(segmentForm.criteria.customFields).map(([field, value], index) => (
                        <div key={index} className="flex gap-2 items-center">
                          <input
                            type="text"
                            placeholder="Field name"
                            value={field}
                            className="flex-1 border rounded px-2 py-1 text-sm bg-gray-100"
                            readOnly
                          />
                          <input
                            type="text"
                            placeholder="Value"
                            value={value}
                            onChange={(e) => {
                              const newCustomFields = { ...segmentForm.criteria.customFields };
                              newCustomFields[field] = e.target.value;
                              handleCriteriaChange('customFields', newCustomFields);
                            }}
                            className="flex-1 border rounded px-2 py-1 text-sm"
                          />
                          <button
                            onClick={() => {
                              const newCustomFields = { ...segmentForm.criteria.customFields };
                              delete newCustomFields[field];
                              handleCriteriaChange('customFields', newCustomFields);
                            }}
                            className="text-red-600 hover:text-red-800 px-2"
                          >
                            ❌
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                  
                  <button
                    onClick={() => {
                      const fieldName = prompt('Enter custom field name:');
                      if (fieldName) {
                        const newCustomFields = { ...segmentForm.criteria.customFields } || {};
                        newCustomFields[fieldName] = '';
                        handleCriteriaChange('customFields', newCustomFields);
                      }
                    }}
                    className="text-blue-600 text-sm hover:underline"
                  >
                    ➕ Add Custom Field Filter
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="mt-8 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!segmentForm.name.trim()}
            className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isEditing ? 'Update Segment' : 'Create Segment'}
          </button>
        </div>
      </div>
    </div>
  );
};

// Preview Modal Component
const SegmentPreviewModal = ({ show, onClose, segment, previewData }) => {
  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex justify-center items-start pt-10 z-50">
      <div className="bg-white p-6 rounded-lg shadow-xl w-full max-w-6xl max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h3 className="text-xl font-bold">👁️ Preview: {segment?.name}</h3>
            <p className="text-gray-600">{segment?.description}</p>
          </div>
          <button onClick={onClose} className="text-gray-600 hover:text-black text-xl">✖</button>
        </div>

        <div className="mb-4 p-3 bg-blue-50 rounded">
          <div className="text-lg font-semibold text-blue-800">
            {previewData.length.toLocaleString()} subscribers match this segment
          </div>
        </div>

        {previewData.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm border">
              <thead className="bg-gray-100">
                <tr>
                  <th className="p-2 border text-left">Name</th>
                  <th className="p-2 border text-left">Email</th>
                  <th className="p-2 border text-left">List</th>
                  <th className="p-2 border text-left">Status</th>
                  <th className="p-2 border text-left">Joined</th>
                  <th className="p-2 border text-left">Custom Fields</th>
                </tr>
              </thead>
              <tbody>
                {previewData.slice(0, 50).map((subscriber, index) => (
                  <tr key={index} className="hover:bg-gray-50">
                    <td className="p-2 border">
                      {`${subscriber.standard_fields?.first_name || ''} ${subscriber.standard_fields?.last_name || ''}`.trim() || '-'}
                    </td>
                    <td className="p-2 border">{subscriber.email}</td>
                    <td className="p-2 border">
                      <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs">
                        {subscriber.list}
                      </span>
                    </td>
                    <td className="p-2 border">
                      <span className={`px-2 py-1 rounded text-xs ${
                        subscriber.status === 'active' ? 'bg-green-100 text-green-800' :
                        subscriber.status === 'unsubscribed' ? 'bg-red-100 text-red-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {subscriber.status || 'active'}
                      </span>
                    </td>
                    <td className="p-2 border text-xs text-gray-600">
                      {subscriber.created_at ? new Date(subscriber.created_at).toLocaleDateString() : '-'}
                    </td>
                    <td className="p-2 border">
                      {subscriber.custom_fields && Object.keys(subscriber.custom_fields).length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(subscriber.custom_fields).slice(0, 2).map(([key, value]) => (
                            <span key={key} className="bg-purple-100 text-purple-700 px-1 py-0.5 rounded text-xs">
                              {key}: {value}
                            </span>
                          ))}
                          {Object.keys(subscriber.custom_fields).length > 2 && (
                            <span className="text-gray-500 text-xs">
                              +{Object.keys(subscriber.custom_fields).length - 2}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-gray-400 text-xs">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {previewData.length > 50 && (
              <div className="p-3 text-center text-gray-500">
                Showing first 50 of {previewData.length.toLocaleString()} subscribers
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500">
            <div className="text-4xl mb-4">🔍</div>
            <p>No subscribers match this segment criteria</p>
          </div>
        )}

        <div className="mt-6 flex justify-end">
          <button
            onClick={onClose}
            className="bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700"
          >
            Close Preview
          </button>
        </div>
      </div>
    </div>
  );
};

