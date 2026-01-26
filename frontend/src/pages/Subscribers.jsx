import { useEffect, useState, useRef, useCallback } from 'react';
import { v4 as uuidv4 } from "uuid";
import API from '../api';
import Papa from 'papaparse';
import { useNavigate } from 'react-router-dom';

export default function Subscribers() {
  const navigate = useNavigate();
  const [subscribers, setSubscribers] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);

  const [isSearchMode, setIsSearchMode] = useState(false);
  const [currentSearchTerm, setCurrentSearchTerm] = useState('');
  const [searchStats, setSearchStats] = useState(null);
  const [searchWarning, setSearchWarning] = useState('');
  const [searchStrategy, setSearchStrategy] = useState('smart');
  const searchTimeoutRef = useRef(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [csvHeaders, setCsvHeaders] = useState([]);
  const [csvData, setCsvData] = useState([]);
  const [listName, setListName] = useState('');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState('');
  const [uploadStats, setUploadStats] = useState({ total: 0, processed: 0, speed: 0, method: '' });
  const [subscriberPage, setSubscriberPage] = useState(1);
  const [subscriberTotalPages, setSubscriberTotalPages] = useState(1);
  const [subscriberTotal, setSubscriberTotal] = useState(0);
  

  // Field map shape for CSV mapping
  const [fieldMap, setFieldMap] = useState({
    email: '',
    standard: { first_name: '', last_name: '' },
    custom: [],
  });

  const [lists, setLists] = useState([]);
  const [selectedListName, setSelectedListName] = useState('');
  const [selectedSubscribers, setSelectedSubscribers] = useState([]);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingSubscriber, setEditingSubscriber] = useState(null);
  const [processingJobs, setProcessingJobs] = useState(new Map());
  const [showProcessingBanner, setShowProcessingBanner] = useState(false);
  const pollingIntervalRef = useRef(null);

  // Subscriber form shape for single add/edit
  const emptyForm = {
    email: '',
    list: '',
    status: 'active',
    standard_fields: { first_name: '', last_name: '' },
    custom_fields: {},
  };
  const [subscriberForm, setSubscriberForm] = useState(emptyForm);

  const [showAllSubscribers, setShowAllSubscribers] = useState(false);
  const [allSubscribers, setAllSubscribers] = useState([]);
  const [error, setError] = useState('');

  const validateEmail = (email) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

  // Debounce Hook
  const useDebounce = (value, delay) => {
    const [debouncedValue, setDebouncedValue] = useState(value);
    useEffect(() => {
      const handler = setTimeout(() => setDebouncedValue(value), delay);
      return () => clearTimeout(handler);
    }, [value, delay]);
    return debouncedValue;
  };
  const debouncedSearchTerm = useDebounce(searchTerm, 300);

  // Add this useEffect to start polling when component mounts
  useEffect(() => {
    const checkInitialJobs = async () => {
      try {
        console.log('🔍 Checking for initial jobs...');
        const response = await API.get('/subscribers/jobs/status');
        const jobs = response.data.jobs || [];

        console.log('📊 Initial jobs found:', jobs.length);
        console.log('📊 Job statuses:', jobs.map(j => `${j.list_name}: ${j.status}`));

        const updatedJobs = new Map();
        let hasActiveJobs = false;

        jobs.forEach(job => {
          updatedJobs.set(job.list_name, job);
          if (['pending', 'processing', 'failed'].includes(job.status)) {
            hasActiveJobs = true;
            console.log(`✅ Active job found: ${job.list_name} - ${job.status}`);
          }
        });

        setProcessingJobs(updatedJobs);
        setShowProcessingBanner(hasActiveJobs);

        if (hasActiveJobs) {
          console.log('🚀 Starting job polling for active jobs');
          startPollingJobs();
        } else {
          console.log('💤 No active jobs found');
        }
      } catch (error) {
        console.error('Initial job check failed:', error);
      }
    };

    // Check for jobs when component mounts
    checkInitialJobs();

    return () => {
      console.log('🛑 Component unmounting, stopping polling');
      stopPollingJobs();
    };
  }, []); // Run once on mount

  // Add this function to your Subscribers component
  const stopPollingJobs = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
      console.log('🛑 Polling stopped');
    }
  };

  // ✅ ENHANCED Job Status Polling with Performance Metrics
  const pollJobStatus = async (jobId) => {
    try {
      const response = await API.get('/subscribers/jobs/status');
      const jobs = response.data.jobs || [];
      const job = jobs.find(j => j.job_id === jobId);

      if (!job) return;

      // ✅ HANDLE FAILED STATUS with detailed info
      if (job.status === 'failed') {
        setUploadStatus('');
        setUploadProgress(0);

        const failureMessage = job.error_message || 'Upload processing failed';
        const canRecover = job.recovery_available;
        const failedAt = job.failed_at_record || 0;
        const total = job.total_records || 0;
        const recoveryInfo = job.recovery_info || {};

        alert(`❌ UPLOAD FAILED\n\n` +
          `📊 Progress: ${failedAt.toLocaleString()} / ${total.toLocaleString()} processed\n` +
          `❌ Error: ${failureMessage}\n\n` +
          `🔧 Recovery Options:\n` +
          `${canRecover ? '• Manual retry available\n' : ''}` +
          `${recoveryInfo.optimization_available ? '• Optimized processing available\n' : ''}` +
          `${recoveryInfo.estimated_recovery_time_minutes ? `• Estimated recovery time: ${recoveryInfo.estimated_recovery_time_minutes} minutes\n` : ''}` +
          `\n💡 Check the main page for retry options or auto-recovery will handle this.`);

        return; // Stop polling
      }

      // ✅ HANDLE SUCCESSFUL COMPLETION with performance info
      if (job.status === 'completed') {
        setUploadStatus('');
        setUploadProgress(100);

        const speed = job.records_per_second || 0;
        const processingTime = job.processing_time_seconds || 0;
        const optimized = job.optimization_used ? ' (Optimized)' : '';

        alert(`✅ UPLOAD COMPLETE!${optimized}\n\n` +
          `📊 ${job.final_processed?.toLocaleString() || job.processed} subscribers processed\n` +
          `⚡ Speed: ${speed.toLocaleString()} records/sec\n` +
          `⏱️ Time: ${processingTime.toFixed(1)} seconds\n` +
          `🔧 Method: ${job.performance_display?.method_text || 'Standard'}`);

        fetchLists();
        return; // Stop polling
      }

      // ✅ HANDLE ONGOING PROCESSING with enhanced progress
      if (job.status === 'processing') {
        const progressPercent = job.progress || 0;
        setUploadProgress(progressPercent);

        const speed = job.records_per_second || 0;
        const method = job.performance_display?.method_text || 'Processing';

        setUploadStats({
          total: job.total || 0,
          processed: job.processed || 0,
          speed: speed,
          method: method
        });

        setTimeout(() => pollJobStatus(jobId), 3000);
      }

      // ✅ HANDLE STUCK JOBS
      if (job.is_stuck) {
        alert(`⚠️ JOB APPEARS STUCK\n\n` +
          `Job: ${job.list_name}\n` +
          `Status: No activity for 5+ minutes\n\n` +
          `🔧 Recommended Actions:\n` +
          `• Wait a few more minutes\n` +
          `• Check system resources\n` +
          `• Manual retry may be needed`);

        setTimeout(() => pollJobStatus(jobId), 2000);
      }

    } catch (error) {
      console.error('Enhanced job status polling failed:', error);
      setTimeout(() => pollJobStatus(jobId), 2000);
    }
  };

  // ✅ ENHANCED Progress Indicator with Performance Metrics
  const ProgressIndicator = () => {
    if (!uploadStatus) return null;

    return (
      <div className="mb-4 p-3 bg-gray-50 rounded border">
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm font-medium">
            {uploadStatus === 'processing' && '⚙️ Processing CSV...'}
            {uploadStatus === 'uploading' && `📤 ${uploadStats.method || 'Uploading'} subscribers...`}
            {uploadStatus === 'ready' && '✅ Ready to map fields'}
          </span>
          <span className="text-sm text-gray-600">
            {uploadStats.processed?.toLocaleString()} / {uploadStats.total?.toLocaleString()}
            {uploadStats.speed > 0 && (
              <span className="text-blue-600 ml-2">
                ⚡ {uploadStats.speed.toLocaleString()}/sec
              </span>
            )}
          </span>
        </div>

        <div className="w-full bg-gray-200 rounded-full h-3 mb-2">
          <div
            className={`h-3 rounded-full transition-all duration-300 ${uploadStatus === 'uploading' ? 'bg-blue-600' : 'bg-green-600'
              }`}
            style={{ width: `${uploadProgress}%` }}
          ></div>
        </div>

        {uploadStats.method && (
          <div className="text-xs text-gray-500">
            Processing Method: {uploadStats.method}
          </div>
        )}
      </div>
    );
  };

  // Job Management Functions
  // ✅ FIXED: Better polling with smarter stuck detection
  const startPollingJobs = () => {
    if (pollingIntervalRef.current) return;

    pollingIntervalRef.current = setInterval(async () => {
      try {
        const response = await API.get('/subscribers/jobs/status');
        const jobs = response.data.jobs || [];

        const updatedJobs = new Map();
        let hasActiveJobs = false;

        jobs.forEach(job => {
          updatedJobs.set(job.list_name, job);

          if (['pending', 'processing'].includes(job.status)) {
            hasActiveJobs = true;

            const processed = job.processed_records || job.processed || 0;
            const total = job.total_records || job.total || 1;
            const progress = job.progress || 0;
            const speed = job.records_per_second || 0;
            const phase = job.processing_phase || 'processing';

            // ✅ CRITICAL FIX: Multi-factor working detection
            const now = new Date();
            const lastUpdate = new Date(job.updated_at || job.created_at);
            const timeSinceUpdate = (now - lastUpdate) / (1000 * 60); // minutes

            // ✅ NEW: Working detection (if ANY of these are true, it's working)
            const isWorking = (
              progress > 0 ||                           // Has any progress
              processed > 0 ||                          // Has processed any records
              speed > 0 ||                              // Has current speed
              job.background_task_started ||            // Task started
              phase !== 'initializing' ||              // Past init phase
              timeSinceUpdate < 10 ||                   // Recent activity (10 min)
              job.status === 'pending'                  // Queued jobs aren't stuck
            );

            // ✅ FIXED: Only mark as stuck if ALL criteria met AND not working
            const isReallyStuck = (
              !isWorking &&                            // Must not be working
              job.status === 'processing' &&           // Must be processing
              timeSinceUpdate > 20 &&                  // No update for 20+ minutes
              progress === 0 &&                        // Absolutely no progress
              processed === 0 &&                       // No records processed
              phase === 'initializing'                 // Still initializing
            );

            job.is_working = isWorking;
            job.is_stuck = isReallyStuck;

            // ✅ DEBUG: Log analysis for troubleshooting
            if (timeSinceUpdate > 5) {
              console.log(`🔍 ${job.list_name} analysis:`, {
                minutes_old: timeSinceUpdate.toFixed(1),
                progress: progress.toFixed(1) + '%',
                processed: processed.toLocaleString(),
                speed: speed.toLocaleString() + '/sec',
                phase: phase,
                is_working: isWorking,
                is_stuck: isReallyStuck
              });
            }
          }
        });

        setProcessingJobs(updatedJobs);
        setShowProcessingBanner(hasActiveJobs || Array.from(updatedJobs.values()).some(job => job.status === 'failed'));

        if (!hasActiveJobs) {
          console.log('✅ No active jobs, stopping polling');
          stopPollingJobs();
        }

      } catch (error) {
        console.error('Job polling failed:', error);
      }
    }, 2000);
  };
  


  // ✅ ENHANCED Processing Banner with Manual Cleanup and Real-time Data
  // ✅ FIXED: Better banner with smarter display logic
  const ProcessingBanner = () => {
    if (!showProcessingBanner) return null;

    const activeJobs = Array.from(processingJobs.values()).filter(job =>
      ['pending', 'processing'].includes(job.status)
    );

    const failedJobs = Array.from(processingJobs.values()).filter(job =>
      job.status === 'failed'
    );

    const allDisplayJobs = [...activeJobs, ...failedJobs];

    if (allDisplayJobs.length === 0) return null;

    return (
      <div className="mb-4 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-semibold text-blue-800">
            🚀 Background Processing Status ({activeJobs.length} active, {failedJobs.length} failed)
          </h4>
          <div className="flex gap-2">
            {failedJobs.length > 0 && (
              <button
                onClick={async () => {
                  try {
                    const response = await API.delete('/subscribers/jobs/clear-all');
                    if (response.status === 200) {
                      alert(`✅ Cleared ${failedJobs.length} failed jobs!`);
                      setProcessingJobs(new Map());
                      setShowProcessingBanner(false);
                    } else {
                      alert('❌ Failed to clear jobs');
                    }
                  } catch (error) {
                    alert('❌ Error: ' + error.message);
                  }
                }}
                className="text-xs bg-red-600 text-white px-2 py-1 rounded hover:bg-red-700"
              >
                🗑️ Clear {failedJobs.length} Failed Jobs
              </button>
            )}

            {/* ✅ MANUAL cleanup button - only show if needed */}
            {activeJobs.some(job => job.is_really_stuck) && (
              <button
                onClick={async () => {
                  if (confirm('⚠️ Force cleanup stuck jobs? This will mark them as failed.')) {
                    try {
                      const response = await API.post('/subscribers/jobs/cleanup-stuck');
                      alert(`🧹 Cleanup result: ${response.data.message}`);
                      // Refresh after cleanup
                      setTimeout(() => window.location.reload(), 1000);
                    } catch (error) {
                      alert(`❌ Cleanup failed: ${error.message}`);
                    }
                  }
                }}
                className="text-xs bg-orange-600 text-white px-2 py-1 rounded hover:bg-orange-700"
              >
                🔧 Fix Stuck Jobs
              </button>
            )}

            <button
              onClick={() => setShowProcessingBanner(false)}
              className="text-blue-600 hover:text-blue-800 text-sm"
            >
              Hide
            </button>
          </div>
        </div>

        <div className="space-y-3">
          {/* ✅ ACTIVE JOBS - Show with progress */}
          {activeJobs.map(job => {
            const processed = job.processed_records || job.processed || 0;
            const total = job.total_records || job.total || 1;
            const progress = Math.min((processed / total) * 100, 100);
            const remaining = Math.max(0, total - processed);
            const speed = job.records_per_second || 0;
            const estimatedMinutesLeft = speed > 0 ? Math.ceil(remaining / speed / 60) : 0;

            const isReallyStuck = job.is_really_stuck && progress === 0;

            return (
              <div key={job.list_name} className={`rounded p-3 border ${isReallyStuck ? 'bg-orange-50 border-orange-200' : 'bg-white'
                }`}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-3">
                    {isReallyStuck ? (
                      <div className="h-4 w-4 bg-orange-500 rounded-full animate-pulse"></div>
                    ) : (
                      <div className="animate-spin h-4 w-4 border-2 border-blue-600 border-t-transparent rounded-full"></div>
                    )}
                    <span className="font-medium">{job.list_name}</span>
                    <span className={`text-xs px-2 py-1 rounded ${isReallyStuck ? 'bg-orange-100 text-orange-800' :
                        job.status === 'pending' ? 'bg-yellow-100 text-yellow-800' :
                          'bg-blue-100 text-blue-800'
                      }`}>
                      {isReallyStuck ? '⏳ May be stuck' :
                        job.status === 'pending' ? 'Queued' : 'Processing'}
                    </span>
                  </div>

                  <div className="text-right text-sm">
                    <div className="text-gray-800 font-medium">
                      📊 {processed.toLocaleString()} / {total.toLocaleString()}
                    </div>
                    <div className="text-blue-600 text-xs">
                      {speed > 0 ? (
                        <span>⚡ {speed.toLocaleString()}/sec</span>
                      ) : progress > 0 ? (
                        <span>🔄 Processing...</span>
                      ) : (
                        <span>⏳ Starting...</span>
                      )}
                    </div>
                    {estimatedMinutesLeft > 0 && (
                      <div className="text-gray-500 text-xs">
                        ⏱️ ~{estimatedMinutesLeft}m left
                      </div>
                    )}
                  </div>
                </div>

                <div className="w-full bg-gray-200 rounded-full h-3 mb-2">
                  <div
                    className={`h-3 rounded-full transition-all duration-1000 relative ${isReallyStuck ? 'bg-orange-500' : 'bg-blue-600'
                      }`}
                    style={{ width: `${Math.max(progress, 2)}%` }}
                  >
                    <span className="absolute inset-0 flex items-center justify-center text-xs text-white font-medium">
                      {progress.toFixed(1)}%
                    </span>
                  </div>
                </div>

                <div className="flex justify-between items-center text-xs text-gray-600">
                  <span>Method: {job.processing_method || 'Standard'}</span>
                  <span className="text-orange-600">
                    📋 {remaining.toLocaleString()} remaining
                  </span>
                </div>
              </div>
            );
          })}

          {/* ✅ FAILED JOBS - Show separately */}
          {failedJobs.map(job => (
            <div key={`failed-${job.list_name}`} className="bg-red-50 border border-red-200 rounded p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="h-4 w-4 bg-red-500 rounded-full"></div>
                  <span className="font-medium text-red-800">{job.list_name}</span>
                  <span className="text-xs bg-red-100 text-red-800 px-2 py-1 rounded">
                    ❌ Failed
                  </span>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={async () => {
                      if (confirm(`Retry failed job for "${job.list_name}"?`)) {
                        try {
                          const response = await API.post(`/subscribers/jobs/${job.job_id}/force-retry`);
                          alert(`✅ Retry initiated for ${job.list_name}`);
                          // Refresh status
                          setTimeout(() => window.location.reload(), 1000);
                        } catch (error) {
                          alert(`❌ Retry failed: ${error.message}`);
                        }
                      }
                    }}
                    className="text-xs bg-orange-600 text-white px-2 py-1 rounded hover:bg-orange-700"
                  >
                    🔄 Retry
                  </button>
                  <button
                    onClick={async () => {
                      try {
                        await API.delete(`/subscribers/jobs/${job.job_id}`);
                        alert(`✅ Cleared failed job: ${job.list_name}`);
                        // Refresh
                        setTimeout(() => window.location.reload(), 1000);
                      } catch (error) {
                        alert(`❌ Clear failed: ${error.message}`);
                      }
                    }}
                    className="text-xs bg-gray-600 text-white px-2 py-1 rounded hover:bg-gray-700"
                  >
                    🗑️ Clear
                  </button>
                </div>
              </div>
              {job.error_message && (
                <div className="mt-2 text-xs text-red-600">
                  Error: {job.error_message}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="mt-3 text-xs text-blue-600">
          💡 Jobs process in background. You can safely refresh the browser.
          {activeJobs.some(job => job.optimization_used) && (
            <span className="block mt-1">⚡ Optimized processing active!</span>
          )}
        </div>
      </div>
    );
  };
  
  // Virtualized Table Components
  const VirtualizedTable = ({ data, renderRow, rowHeight = 40, height = 400 }) => {
    const [scrollTop, setScrollTop] = useState(0);
    const VISIBLE_ROWS = Math.ceil(height / rowHeight);
    const BUFFER = 5;

    const start = Math.max(0, Math.floor(scrollTop / rowHeight) - BUFFER);
    const end = Math.min(data.length, start + VISIBLE_ROWS + BUFFER * 2);
    const visible = data.slice(start, end);

    return (
      <div style={{ height, overflow: "auto" }} onScroll={(e) => setScrollTop(e.target.scrollTop)}>
        <div style={{ height: `${data.length * rowHeight}px`, position: "relative" }}>
          <table className="w-full table-auto text-sm absolute top-0 left-0">
            <tbody style={{ transform: `translateY(${start * rowHeight}px)` }}>
              {visible.map((item, idx) => renderRow(item, idx))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const ITEMS_PER_PAGE = 50;
  const [currentPage, setCurrentPage] = useState(1);

  // Data fetching
  const fetchAllSubscribers = async (page = 1, searchTerm = '') => {
    try {
      setLoading(true);

      const isSearch = searchTerm.trim().length > 0;
      setIsSearchMode(isSearch);
      setCurrentSearchTerm(searchTerm);

      const params = {
        page: page,
        limit: 50,
        search_mode: searchStrategy,
        ...(searchTerm && { search: searchTerm })
      };

      const res = await API.get('/subscribers/search', { params });

      setAllSubscribers(res.data.subscribers || []);

      const { pagination, performance } = res.data;

      setSubscriberPage(page);
      setSubscriberTotalPages(pagination.total_pages || Math.ceil(pagination.total / 50));
      setSubscriberTotal(pagination.total || 0);
      setSearchStats(performance);

      updateSearchWarnings(searchTerm, pagination, performance);
    } catch (err) {
      console.error('Error fetching subscribers', err);
      setSearchWarning('Search failed. Please try again.');
      setError('Search failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLists();
  }, []);

  const fetchLists = async () => {
    try {
      const res = await API.get('/subscribers/lists');
      setLists(res.data || []);
    } catch (err) {
      console.error('Error fetching lists', err);
      setLists([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSearchAllSubscribers = () => {
    setShowAllSubscribers(true);
    setSearchTerm('');
    setCurrentSearchTerm('');
    setSearchWarning('');
    setError('');
    setSubscriberPage(1);
    fetchAllSubscribers(1, '');
  };

  const handleSearchChange = (value) => {
    setSearchTerm(value);

    if (showAllSubscribers) {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }

      searchTimeoutRef.current = setTimeout(() => {
        setSubscriberPage(1);
        fetchAllSubscribers(1, value);
      }, 500);
    }
  };

  const analyzeSearchTerm = (term) => {
    if (!term) return { isExact: false, specificity: 'none' };

    const isEmail = term.includes('@') && term.includes('.');
    const isId = term.length === 24 && /^[0-9a-fA-F]+$/.test(term);
    const isPhone = term.replace(/\D/g, '').length >= 10;

    return {
      isExact: isEmail || isId || isPhone,
      specificity: isEmail || isId ? 'exact' :
        term.length >= 8 ? 'specific' :
          term.length >= 4 ? 'general' : 'broad',
      searchType: isEmail ? 'email' : isId ? 'id' : isPhone ? 'phone' : 'text'
    };
  };

  const updateSearchWarnings = (searchTerm, pagination, performance) => {
    if (!searchTerm) {
      setSearchWarning('');
      return;
    }

    const hints = analyzeSearchTerm(searchTerm);

    if (hints.specificity === 'broad' && pagination.total > 1000) {
      setSearchWarning(`⚠️ "${searchTerm}" is very broad (${pagination.total}+ results). Consider more specific terms for better performance.`);
    } else if (pagination.total === 0) {
      setSearchWarning(`No results found for "${searchTerm}". Try partial matches or check spelling.`);
    } else if (!pagination.has_more && pagination.total > 5000) {
      setSearchWarning(`✅ Showing all ${pagination.total} results. Consider refining your search for better performance.`);
    } else {
      setSearchWarning('');
    }
  };

  const renderResultsInfo = () => {
    if (!showAllSubscribers) return null;

    const startItem = ((subscriberPage - 1) * 50) + 1;
    const endItem = Math.min(subscriberPage * 50, subscriberTotal);

    return (
      <div className="mb-2 flex items-center justify-between text-sm">
        <div className="flex items-center gap-4">
          <div className={`px-3 py-1 rounded ${isSearchMode ? 'bg-green-50 text-green-700' : 'bg-blue-50 text-blue-700'
            }`}>
            {isSearchMode ?
              `Found ${subscriberTotal} matches` :
              `Total ${subscriberTotal} subscribers`
            }
          </div>

          <div className="text-gray-600">
            Showing {startItem}-{endItem} of {subscriberTotal}
          </div>

          {searchStats && (
            <div className="text-gray-600">
              Strategy: {searchStats.strategy} | {searchStats.query_time}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <select
            value={searchStrategy}
            onChange={(e) => setSearchStrategy(e.target.value)}
            className="text-xs border rounded px-2 py-1"
          >
            <option value="smart">Smart</option>
            <option value="exact">Exact Only</option>
          </select>
        </div>
      </div>
    );
  };

  const SubscriberPagination = () => {
    if (!showAllSubscribers || subscriberTotalPages <= 1) return null;

    const handlePageChange = (newPage) => {
      if (newPage >= 1 && newPage <= subscriberTotalPages) {
        setSubscriberPage(newPage);
        fetchAllSubscribers(newPage, currentSearchTerm);
      }
    };

    const getPageNumbers = () => {
      const pages = [];
      const maxVisible = 5;

      let start = Math.max(1, subscriberPage - Math.floor(maxVisible / 2));
      let end = Math.min(subscriberTotalPages, start + maxVisible - 1);

      if (end - start + 1 < maxVisible) {
        start = Math.max(1, end - maxVisible + 1);
      }

      for (let i = start; i <= end; i++) {
        pages.push(i);
      }

      return pages;
    };

    return (
      <div className="flex justify-between items-center mt-4">
        <div className="text-sm text-gray-600">
          Page {subscriberPage} of {subscriberTotalPages}
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => handlePageChange(1)}
            disabled={subscriberPage === 1}
            className="px-3 py-1 text-xs border rounded disabled:opacity-50 hover:bg-gray-50"
          >
            First
          </button>
          <button
            onClick={() => handlePageChange(subscriberPage - 1)}
            disabled={subscriberPage === 1}
            className="px-3 py-1 text-xs border rounded disabled:opacity-50 hover:bg-gray-50"
          >
            Previous
          </button>

          {getPageNumbers().map(page => (
            <button
              key={page}
              onClick={() => handlePageChange(page)}
              className={`px-3 py-1 text-xs border rounded ${page === subscriberPage
                  ? 'bg-blue-600 text-white'
                  : 'hover:bg-gray-50'
                }`}
            >
              {page}
            </button>
          ))}

          <button
            onClick={() => handlePageChange(subscriberPage + 1)}
            disabled={subscriberPage === subscriberTotalPages}
            className="px-3 py-1 text-xs border rounded disabled:opacity-50 hover:bg-gray-50"
          >
            Next
          </button>
          <button
            onClick={() => handlePageChange(subscriberTotalPages)}
            disabled={subscriberPage === subscriberTotalPages}
            className="px-3 py-1 text-xs border rounded disabled:opacity-50 hover:bg-gray-50"
          >
            Last
          </button>
        </div>
      </div>
    );
  };

  // CSV upload handlers
  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploadStatus('processing');
    setUploadProgress(10);

    Papa.parse(file, {
      complete: (results) => {
        if (results.data && results.data.length > 0) {
          const headers = results.data[0];
          const data = results.data.slice(1).filter(row => row.length > 1);

          if (headers.length === 0 || data.length === 0) {
            alert('CSV file appears to be empty or invalid');
            setUploadStatus('');
            return;
          }

          setCsvHeaders(headers);
          setCsvData(data);
          setUploadStatus('ready');
          setUploadProgress(100);
          setUploadStats({ total: data.length, processed: 0 });

          if (headers.includes('email') || headers.includes('Email') || headers.includes('EMAIL')) {
            const emailColumn = headers.find(h => h.toLowerCase() === 'email');
            setFieldMap(prev => ({ ...prev, email: emailColumn }));
          }
        }
      },
      header: false,
      skipEmptyLines: true,
      error: (err) => {
        console.error('CSV parse error:', err);
        alert('Failed to parse CSV file');
        setUploadStatus('');
      }
    });
  };

  // ✅ ENHANCED Upload Handler for Optimized Backend
  const handleUploadList = async () => {
    if (!listName.trim()) {
      alert('List name is required');
      return;
    }
    if (!fieldMap.email || !csvHeaders.includes(fieldMap.email)) {
      alert('Email field must be mapped correctly');
      return;
    }

    setUploadStatus('uploading');
    setUploadProgress(0);

    const formatted = csvData
      .map((row) => {
        const subscriber = {
          email: row[csvHeaders.indexOf(fieldMap.email)]?.trim(),
          list: listName.trim(),
          status: 'active',
          standard_fields: {},
          custom_fields: {},
        };

        Object.entries(fieldMap.standard || {}).forEach(([field, column]) => {
          if (column && csvHeaders.includes(column)) {
            const value = row[csvHeaders.indexOf(column)];
            if (value) {
              subscriber.standard_fields[field] = String(value).trim();
            }
          }
        });

        (fieldMap.custom || []).forEach((f) => {
          if (f.label && f.value && csvHeaders.includes(f.value)) {
            const value = row[csvHeaders.indexOf(f.value)];
            if (value) {
              subscriber.custom_fields[f.label] = String(value).trim();
            }
          }
        });

        return subscriber;
      })
      .filter((sub) => sub.email);

    // ✅ ALWAYS use background processing for large files (optimized backend handles this)
    const useBackgroundProcessing = formatted.length > 10000; // Lower threshold

    if (useBackgroundProcessing) {
      try {
        const uploadPayload = {
          list_name: listName.trim(),
          subscribers: formatted,
          processing_mode: 'background'
        };

        const response = await API.post('/subscribers/background-upload', uploadPayload);
        const data = response.data;

        // ✅ Enhanced success message with optimization info
        const optimizationInfo = data.optimization_enabled ?
          `\n🚀 OPTIMIZATION ENABLED!\n• ${data.expected_speed}\n• ${data.processing_method}\n${data.parallel_processing ? '• Parallel processing\n' : ''}` : '';

        alert(`✅ UPLOAD STARTED!${optimizationInfo}\n\n` +
          `📊 ${formatted.length.toLocaleString()} subscribers queued\n` +
          `📂 Processing method: ${data.processing_method}\n` +
          `${data.chunks_created ? `📁 Split into ${data.chunks_created} chunks\n` : ''}` +
          `⏱️ Estimated time: ${data.estimated_completion_minutes} minutes\n\n` +
          `💡 Processing continues in background.\n` +
          `${data.can_refresh_browser ? 'Safe to refresh browser!' : ''}`);

        // Reset and start monitoring
        setShowUploadModal(false);
        resetUploadModal();

        // Start polling with the job ID
        setTimeout(() => pollJobStatus(data.job_id), 2000);
        startPollingJobs();
        fetchLists();

      } catch (error) {
        console.error('Optimized background upload error:', error);
        const errorMessage = error.response?.data?.detail || 'Unknown error';
        alert(`❌ UPLOAD FAILED\n\nError: ${errorMessage}\n\n💡 Try again or contact support if the issue persists.`);
        setUploadStatus('');
      }
    } else {
      // Use standard chunked processing for smaller files
      const CHUNK_SIZE = 50000;
      const chunks = [];
      for (let i = 0; i < formatted.length; i += CHUNK_SIZE) {
        chunks.push(formatted.slice(i, i + CHUNK_SIZE));
      }

      try {
        let totalProcessed = 0;
        for (let i = 0; i < chunks.length; i++) {
          const chunk = chunks[i];
          const payload = {
            list: listName.trim(),
            subscribers: chunk,
            chunk_info: {
              chunk_number: i + 1,
              total_chunks: chunks.length,
              is_first_chunk: i === 0,
            },
          };

          await API.post('/subscribers/bulk', payload);

          totalProcessed += chunk.length;
          const progress = Math.round((totalProcessed / formatted.length) * 100);
          setUploadProgress(progress);
          setUploadStats({ total: formatted.length, processed: totalProcessed });
        }

        alert(`✅ Successfully uploaded ${totalProcessed.toLocaleString()} subscribers`);
        setShowUploadModal(false);
        resetUploadModal();
        fetchLists();
      } catch (err) {
        alert('Upload failed');
        console.error(err);
        setUploadStatus('');
      }
    }
  };

  const resetUploadModal = () => {
    setCsvHeaders([]);
    setCsvData([]);
    setListName('');
    setUploadProgress(0);
    setUploadStatus('');
    setUploadStats({ total: 0, processed: 0, speed: 0, method: '' });
    setFieldMap({
      email: '',
      standard: { first_name: '', last_name: '' },
      custom: [],
    });
  };

  // ✅ ENHANCED List Row Rendering with ENABLED buttons for processing
  const renderListRowWithStatus = (list, index) => {
    const job = processingJobs.get(list._id);
    const isProcessing = job && ['pending', 'processing'].includes(job.status);
    const isFailed = job && job.status === 'failed';
    const isCompleted = job && job.status === 'completed';
  
    return (
      <tr key={`${list._id}-${index}`} className="border-t hover:bg-gray-50" style={{ height: 40 }}>
        <td className="p-2 font-medium">
          <div className="flex items-center space-x-2">
            <span>{list._id}</span>
            
            {isProcessing && (
              <div className="flex items-center space-x-1">
                <div className="animate-spin h-3 w-3 border border-blue-600 border-t-transparent rounded-full"></div>
                <span className="text-xs text-blue-600 bg-blue-50 px-2 py-1 rounded">
                  {job.status === 'pending' ? 'Queued' : 'Processing'}
                </span>
                {job.optimization_used && (
                  <span className="text-xs text-green-600 bg-green-50 px-1 py-1 rounded">⚡</span>
                )}
              </div>
            )}
            
            {isCompleted && (
              <div className="flex items-center space-x-1">
                <span className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded">
                  ✅ Completed
                </span>
                {job.records_per_second > 0 && (
                  <span className="text-xs text-gray-500">
                    {job.records_per_second.toLocaleString()}/sec
                  </span>
                )}
              </div>
            )}
            
            {isFailed && (
              <div className="flex items-center space-x-1">
                <span className="text-xs text-red-600 bg-red-50 px-2 py-1 rounded">
                  ❌ Failed
                </span>
                {job.recovery_available && (
                  <span className="text-xs text-orange-600 bg-orange-50 px-1 py-1 rounded">
                    🔧 Recoverable
                  </span>
                )}
              </div>
            )}
          </div>
        </td>
        
        <td className="p-2">
          <div className="flex flex-col">
            <span className="font-medium">{list.count.toLocaleString()}</span>
            {isProcessing && (
              <div className="text-xs text-gray-500">
                <span className="text-blue-600">
                  +{(job.processed || 0).toLocaleString()} processing
                </span>
                {job.records_per_second > 0 && (
                  <span className="block text-green-600">
                    ⚡ {job.records_per_second.toLocaleString()}/sec
                  </span>
                )}
              </div>
            )}
            {isCompleted && job.final_processed && (
              <span className="text-xs text-green-600">
                +{job.final_processed.toLocaleString()} added
              </span>
            )}
          </div>
        </td>
        
        <td className="p-2">
          <div className="flex gap-2 flex-wrap">
            {/* ✅ FIX: View button - ALWAYS enabled */}
            <button
              onClick={() => handleViewSubscribers(list._id)}
              className="text-blue-600 hover:underline text-xs px-2 py-1"
              title={isProcessing ? "View existing subscribers (processing continues)" : "View subscribers"}
            >
              👁️ View
            </button>
            
            {/* ✅ FIX: Export button - ALWAYS enabled */}
            <button
              onClick={() => handleExportList(list._id)}
              className="text-green-600 hover:underline text-xs px-2 py-1"
              title={isProcessing ? "Export current subscribers (processing continues)" : "Export list"}
            >
              📥 Export
            </button>
            
            {/* ✅ FIX: Delete button - Show warning for processing lists */}
            <button
              onClick={() => {
                if (isProcessing) {
                  const confirmDelete = confirm(
                    `⚠️ LIST IS CURRENTLY PROCESSING\n\n` +
                    `List: ${list._id}\n` +
                    `Current: ${list.count.toLocaleString()} subscribers\n` +
                    `Processing: +${(job.processed || 0).toLocaleString()} being added\n\n` +
                    `❌ DELETING WILL:\n` +
                    `• Stop the current upload\n` +
                    `• Delete all existing subscribers\n` +
                    `• Cancel the background processing\n\n` +
                    `Are you sure you want to delete this list?`
                  );
                  if (confirmDelete) {
                    handleDelete(list._id);
                  }
                } else {
                  handleDelete(list._id);
                }
              }}
              className={`text-red-600 hover:underline text-xs px-2 py-1 ${
                isProcessing ? 'bg-red-50 rounded' : ''
              }`}
              title={isProcessing ? "⚠️ Will stop processing and delete list" : "Delete list"}
            >
              🗑️ Delete
            </button>
            
            {/* Enhanced retry button for failed jobs */}
            {isFailed && (
              <button
                onClick={async () => {
                  try {
                    const response = await API.post(`/subscribers/jobs/${job.job_id}/force-retry`);
                    alert(`🔄 Retry initiated!\n\n${response.data.message}\n\n` +
                          `Recovery method: ${response.data.recovery_method}\n` +
                          `${response.data.optimization_available ? 'Optimized processing available!' : ''}`);
                    
                    setTimeout(() => {
                      const checkRetryStatus = async () => {
                        try {
                          const statusResponse = await API.get('/subscribers/jobs/status');
                          const retriedJob = statusResponse.data.jobs.find(j => j.job_id === job.job_id);
                          if (retriedJob && retriedJob.status === 'processing') {
                            startPollingJobs();
                          }
                        } catch (error) {
                          console.error('Failed to check retry status:', error);
                        }
                      };
                      checkRetryStatus();
                    }, 2000);
                    
                  } catch (error) {
                    alert(`❌ Retry failed: ${error.response?.data?.detail || error.message}`);
                  }
                }}
                className="text-orange-600 hover:underline text-xs px-2 py-1 bg-orange-50 rounded"
              >
                🔄 Retry
              </button>
            )}
            
            {/* Recovery status button */}
            {job && job.recovery_info && (
              <button
                onClick={() => {
                  const info = job.recovery_info;
                  alert(`🔧 RECOVERY INFO\n\n` +
                        `Method: ${info.method || 'Standard'}\n` +
                        `${info.chunks_remaining ? `Chunks remaining: ${info.chunks_remaining}\n` : ''}` +
                        `Estimated time: ${info.estimated_recovery_time_minutes || 'Unknown'} minutes\n` +
                        `${info.optimization_available ? 'Optimized recovery available!' : ''}`);
                }}
                className="text-blue-600 hover:underline text-xs px-2 py-1"
              >
                ℹ️ Info
              </button>
            )}
          </div>
        </td>
      </tr>
    );
  };
  

  // Other handlers
  const handleViewSubscribers = async (listName) => {
    navigate(`/subscribers/list/${listName}`);
  };

  const handleExportList = async (listName) => {
    try {
      const response = await API.get(`/subscribers/lists/${listName}/export`, {
        responseType: 'blob',
      });

      const blob = new Blob([response.data], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${listName}_subscribers.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert('Failed to export list');
      console.error(err);
    }
  };

  const handleDelete = async (listName) => {
    const confirmDelete = confirm(
      `⚠️ DELETE LIST CONFIRMATION\n\n` +
      `List: ${listName}\n` +
      `This action will:\n` +
      `• Permanently delete ALL subscribers in this list\n` +
      `• Cancel any active upload jobs\n` +
      `• Cannot be undone\n\n` +
      `Are you sure you want to continue?`
    );

    if (!confirmDelete) return;

    try {
      const response = await API.delete(`/subscribers/lists/${listName}`);

      const summary = response.data.deletion_summary;
      const cleanup = response.data.cleanup_actions;

      alert(`✅ DELETION COMPLETED\n\n` +
        `📊 ${summary.subscribers_deleted.toLocaleString()} subscribers deleted\n` +
        `⏱️ Completed in ${summary.deletion_time_seconds} seconds\n` +
        `⚡ Speed: ${response.data.performance.records_per_second.toLocaleString()} records/sec\n` +
        `🛑 Jobs cancelled: ${cleanup.jobs_cancelled}\n` +
        `📝 Audit: Logged`);

      fetchLists();
    } catch (err) {
      const error = err.response?.data;

      if (error?.detail?.active_jobs) {
        const confirmForce = confirm(
          `❌ CANNOT DELETE - ACTIVE JOBS FOUND\n\n` +
          `Active jobs: ${error.detail.active_jobs}\n` +
          `${error.detail.jobs.join('\n')}\n\n` +
          `Do you want to FORCE DELETE anyway?\n` +
          `(This will cancel all active jobs)`
        );

        if (confirmForce) {
          try {
            const response = await API.delete(`/subscribers/lists/${listName}?force=true`);
            alert(`✅ FORCE DELETION COMPLETED\n\n${response.data.message}`);
            fetchLists();
          } catch (forceError) {
            alert(`❌ Force deletion failed: ${forceError.response?.data?.detail || forceError.message}`);
          }
        }
      } else if (error?.detail?.list_size) {
        const confirmLarge = confirm(
          `⚠️ LARGE LIST WARNING\n\n` +
          `List size: ${error.detail.list_size.toLocaleString()} subscribers\n` +
          `This is a very large deletion operation.\n\n` +
          `Do you want to proceed?`
        );

        if (confirmLarge) {
          try {
            const response = await API.delete(`/subscribers/lists/${listName}?force=true`);
            alert(`✅ LARGE LIST DELETION COMPLETED\n\n${response.data.message}`);
            fetchLists();
          } catch (largeError) {
            alert(`❌ Large list deletion failed: ${largeError.response?.data?.detail || largeError.message}`);
          }
        }
      } else {
        alert(`❌ Deletion failed: ${error?.detail || err.message}`);
      }
    }
  };
  
  const handleAddSubscriber = async () => {
    if (!subscriberForm.email || !validateEmail(subscriberForm.email)) {
      alert('Valid email is required');
      return;
    }
    if (!subscriberForm.list.trim()) {
      alert('List name is required');
      return;
    }

    try {
      await API.post('/subscribers/', subscriberForm);
      alert('Subscriber added successfully');
      setShowAddModal(false);
      setSubscriberForm(emptyForm);
      fetchLists();
    } catch (err) {
      const errorMsg = err.response?.data?.detail || 'Failed to add subscriber';
      alert(errorMsg);
    }
  };

  const handleEditSubscriber = async () => {
    if (!subscriberForm.email || !validateEmail(subscriberForm.email)) {
      alert('Valid email is required');
      return;
    }

    try {
      await API.put(`/subscribers/${editingSubscriber._id}`, subscriberForm);
      alert('Subscriber updated successfully');
      setShowAddModal(false);
      setEditingSubscriber(null);
      setSubscriberForm(emptyForm);

      if (showAllSubscribers) {
        fetchAllSubscribers(subscriberPage, currentSearchTerm);
      } else if (showSubscriberModal) {
        handleViewSubscribers(selectedListName);
      }
      fetchLists();
    } catch (err) {
      const errorMsg = err.response?.data?.detail || 'Failed to update subscriber';
      alert(errorMsg);
    }
  };

  const handleDeleteSubscriber = async (subscriberId) => {
    if (!confirm('Delete this subscriber?')) return;

    try {
      await API.delete(`/subscribers/${subscriberId}`);
      alert('Subscriber deleted successfully');

      if (showAllSubscribers) {
        fetchAllSubscribers(subscriberPage, currentSearchTerm);
      } else if (showSubscriberModal) {
        handleViewSubscribers(selectedListName);
      }
      fetchLists();
    } catch (err) {
      alert('Failed to delete subscriber');
    }
  };

  // Main render
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold mb-4">📧 Enhanced Subscriber Management</h1>

      {/* ✅ ENHANCED Processing Banner */}
      <ProcessingBanner />

      {error && <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">{error}</div>}

      {/* Navigation */}
      <div className="mb-6 flex gap-4 flex-wrap">
        <button
          onClick={() => setShowUploadModal(true)}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        >
          📤 Upload CSV
        </button>
        <button
          onClick={() => setShowAddModal(true)}
          className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700"
        >
          ➕ Add Single Subscriber
        </button>
        <button
          onClick={handleSearchAllSubscribers}
          className="bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700"
        >
          🔍 Search All Subscribers
        </button>
        <button onClick={fetchLists} className="bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700">
          🔄 Refresh
        </button>
      </div>

      {/* All Subscribers View */}
      {showAllSubscribers && (
        <div className="mb-8 border rounded-lg p-4 bg-gray-50">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold">🔍 All Subscribers Search</h2>
            <button
              onClick={() => setShowAllSubscribers(false)}
              className="text-gray-600 hover:text-gray-800"
            >
              ✕ Close
            </button>
          </div>

          <div className="mb-4">
            <input
              type="text"
              placeholder="Search by email, name, list..."
              value={searchTerm}
              onChange={(e) => handleSearchChange(e.target.value)}
              className="w-full p-2 border rounded"
            />
          </div>

          {searchWarning && (
            <div className="mb-4 p-3 bg-yellow-100 border-l-4 border-yellow-500 text-yellow-700">
              {searchWarning}
            </div>
          )}

          {renderResultsInfo()}

          <div className="bg-white rounded border max-h-96 overflow-auto">
            {loading ? (
              <div className="flex justify-center items-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                <span className="ml-2">Searching...</span>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-gray-100 sticky top-0">
                  <tr>
                    <th className="p-2 text-left">Email</th>
                    <th className="p-2 text-left">List</th>
                    <th className="p-2 text-left">Status</th>
                    <th className="p-2 text-left">Name</th>
                    <th className="p-2 text-left">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {allSubscribers.map((sub, idx) => (
                    <tr key={sub._id} className="border-t hover:bg-gray-50">
                      <td className="p-2">{sub.email}</td>
                      <td className="p-2">{sub.list}</td>
                      <td className="p-2">
                        <span className={`px-2 py-1 rounded text-xs ${sub.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                          }`}>
                          {sub.status}
                        </span>
                      </td>
                      <td className="p-2">
                        {[sub.standard_fields?.first_name, sub.standard_fields?.last_name].filter(Boolean).join(' ') || '-'}
                      </td>
                      <td className="p-2">
                        <div className="flex gap-2">
                          <button
                            onClick={() => {
                              setEditingSubscriber(sub);
                              setSubscriberForm({
                                email: sub.email,
                                list: sub.list,
                                status: sub.status,
                                standard_fields: sub.standard_fields || {},
                                custom_fields: sub.custom_fields || {},
                              });
                              setShowAddModal(true);
                            }}
                            className="text-blue-600 hover:underline text-xs"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDeleteSubscriber(sub._id)}
                            className="text-red-600 hover:underline text-xs"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <SubscriberPagination />
        </div>
      )}

      {/* Lists Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-4 py-3 border-b bg-gray-50">
          <h2 className="font-semibold">📋 Subscriber Lists</h2>
        </div>
        <div className="overflow-auto max-h-96">
          <table className="w-full text-sm">
            <thead className="bg-gray-100 sticky top-0">
              <tr>
                <th className="p-2 text-left">List Name</th>
                <th className="p-2 text-left">Count</th>
                <th className="p-2 text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="3" className="p-4 text-center">
                    <div className="flex justify-center items-center">
                      <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                      <span className="ml-2">Loading lists...</span>
                    </div>
                  </td>
                </tr>
              ) : lists.length === 0 ? (
                <tr>
                  <td colSpan="3" className="p-4 text-center text-gray-500">
                    No subscriber lists found. Upload a CSV to get started.
                  </td>
                </tr>
              ) : (
                lists.map((list, index) => renderListRowWithStatus(list, index))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-4xl w-full max-h-full overflow-y-auto m-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold">📤 Upload CSV</h2>
              <button
                onClick={() => {
                  setShowUploadModal(false);
                  resetUploadModal();
                }}
                className="text-gray-500 hover:text-gray-700 text-xl"
              >
                ✕
              </button>
            </div>

            {/* ✅ ENHANCED Progress Indicator */}
            <ProgressIndicator />

            {uploadStatus === '' && (
              <div className="mb-4">
                <label className="block text-sm font-medium mb-2">Choose CSV File</label>
                <input
                  type="file"
                  accept=".csv"
                  onChange={handleFileUpload}
                  className="w-full p-2 border rounded"
                />
              </div>
            )}

            {uploadStatus === 'ready' && csvHeaders.length > 0 && (
              <div>
                <div className="mb-4">
                  <label className="block text-sm font-medium mb-2">List Name</label>
                  <input
                    type="text"
                    value={listName}
                    onChange={(e) => setListName(e.target.value)}
                    placeholder="Enter list name..."
                    className="w-full p-2 border rounded"
                  />
                </div>

                <div className="mb-4">
                  <h3 className="font-medium mb-2">📋 Map CSV Fields</h3>

                  <div className="mb-4">
                    <label className="block text-sm font-medium mb-1">Email Field (Required)</label>
                    <select
                      value={fieldMap.email}
                      onChange={(e) => setFieldMap(prev => ({ ...prev, email: e.target.value }))}
                      className="w-full p-2 border rounded"
                    >
                      <option value="">Select email column...</option>
                      {csvHeaders.map((header, idx) => (
                        <option key={idx} value={header}>{header}</option>
                      ))}
                    </select>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                    <div>
                      <label className="block text-sm font-medium mb-1">First Name</label>
                      <select
                        value={fieldMap.standard.first_name}
                        onChange={(e) => setFieldMap(prev => ({
                          ...prev,
                          standard: { ...prev.standard, first_name: e.target.value }
                        }))}
                        className="w-full p-2 border rounded"
                      >
                        <option value="">Optional...</option>
                        {csvHeaders.map((header, idx) => (
                          <option key={idx} value={header}>{header}</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-medium mb-1">Last Name</label>
                      <select
                        value={fieldMap.standard.last_name}
                        onChange={(e) => setFieldMap(prev => ({
                          ...prev,
                          standard: { ...prev.standard, last_name: e.target.value }
                        }))}
                        className="w-full p-2 border rounded"
                      >
                        <option value="">Optional...</option>
                        {csvHeaders.map((header, idx) => (
                          <option key={idx} value={header}>{header}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="mb-4">
                    <label className="block text-sm font-medium mb-2">Custom Fields</label>
                    {fieldMap.custom.map((customField, idx) => (
                      <div key={idx} className="flex gap-2 mb-2">
                        <input
                          type="text"
                          placeholder="Field name..."
                          value={customField.label}
                          onChange={(e) => {
                            const updated = [...fieldMap.custom];
                            updated[idx] = { ...updated[idx], label: e.target.value };
                            setFieldMap(prev => ({ ...prev, custom: updated }));
                          }}
                          className="flex-1 p-2 border rounded"
                        />
                        <select
                          value={customField.value}
                          onChange={(e) => {
                            const updated = [...fieldMap.custom];
                            updated[idx] = { ...updated[idx], value: e.target.value };
                            setFieldMap(prev => ({ ...prev, custom: updated }));
                          }}
                          className="flex-1 p-2 border rounded"
                        >
                          <option value="">Select column...</option>
                          {csvHeaders.map((header, headerIdx) => (
                            <option key={headerIdx} value={header}>{header}</option>
                          ))}
                        </select>
                        <button
                          onClick={() => {
                            const updated = fieldMap.custom.filter((_, i) => i !== idx);
                            setFieldMap(prev => ({ ...prev, custom: updated }));
                          }}
                          className="px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700"
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                    <button
                      onClick={() => {
                        setFieldMap(prev => ({
                          ...prev,
                          custom: [...prev.custom, { label: '', value: '' }]
                        }));
                      }}
                      className="text-sm text-blue-600 hover:underline"
                    >
                      + Add Custom Field
                    </button>
                  </div>

                  <div className="max-h-32 overflow-auto border rounded p-2 mb-4">
                    <h4 className="text-sm font-medium mb-2">Preview (first 3 rows)</h4>
                    <table className="w-full text-xs">
                      <thead>
                        <tr>
                          {csvHeaders.map((header, idx) => (
                            <th key={idx} className="p-1 text-left border-b">{header}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {csvData.slice(0, 3).map((row, rowIdx) => (
                          <tr key={rowIdx}>
                            {row.map((cell, cellIdx) => (
                              <td key={cellIdx} className="p-1 text-left border-b">{cell}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="flex gap-4">
                    <button
                      onClick={handleUploadList}
                      disabled={!fieldMap.email || !listName.trim()}
                      className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
                    >
                      🚀 Start Upload
                    </button>
                    <button
                      onClick={() => {
                        setShowUploadModal(false);
                        resetUploadModal();
                      }}
                      className="bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Add/Edit Subscriber Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full m-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold">
                {editingSubscriber ? '✏️ Edit Subscriber' : '➕ Add Subscriber'}
              </h2>
              <button
                onClick={() => {
                  setShowAddModal(false);
                  setEditingSubscriber(null);
                  setSubscriberForm(emptyForm);
                }}
                className="text-gray-500 hover:text-gray-700 text-xl"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Email *</label>
                <input
                  type="email"
                  value={subscriberForm.email}
                  onChange={(e) => setSubscriberForm(prev => ({ ...prev, email: e.target.value }))}
                  className="w-full p-2 border rounded"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">List Name *</label>
                <input
                  type="text"
                  value={subscriberForm.list}
                  onChange={(e) => setSubscriberForm(prev => ({ ...prev, list: e.target.value }))}
                  className="w-full p-2 border rounded"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">Status</label>
                <select
                  value={subscriberForm.status}
                  onChange={(e) => setSubscriberForm(prev => ({ ...prev, status: e.target.value }))}
                  className="w-full p-2 border rounded"
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="bounced">Bounced</option>
                  <option value="unsubscribed">Unsubscribed</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">First Name</label>
                <input
                  type="text"
                  value={subscriberForm.standard_fields.first_name}
                  onChange={(e) => setSubscriberForm(prev => ({
                    ...prev,
                    standard_fields: { ...prev.standard_fields, first_name: e.target.value }
                  }))}
                  className="w-full p-2 border rounded"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">Last Name</label>
                <input
                  type="text"
                  value={subscriberForm.standard_fields.last_name}
                  onChange={(e) => setSubscriberForm(prev => ({
                    ...prev,
                    standard_fields: { ...prev.standard_fields, last_name: e.target.value }
                  }))}
                  className="w-full p-2 border rounded"
                />
              </div>

              <div className="flex gap-4">
                <button
                  onClick={editingSubscriber ? handleEditSubscriber : handleAddSubscriber}
                  className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
                >
                  {editingSubscriber ? 'Update' : 'Add'} Subscriber
                </button>
                <button
                  onClick={() => {
                    setShowAddModal(false);
                    setEditingSubscriber(null);
                    setSubscriberForm(emptyForm);
                  }}
                  className="bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}


        
    </div>
  );
}
