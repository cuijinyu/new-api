import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Banner,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Notification,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  TextArea,
  Typography,
} from '@douyinfe/semi-ui';
import { IconPlus, IconRefresh, IconSearch } from '@douyinfe/semi-icons';
import { Database, Download, Play, Sparkles, Trash2 } from 'lucide-react';
import { API, showError, showSuccess } from '../../helpers';

const { Text, Title } = Typography;

const PROVIDER_OPTIONS = [
  { value: 'openrouter', label: 'OpenRouter' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic / Claude' },
  { value: 'google', label: 'Google / Gemini' },
  { value: 'azure', label: 'Azure OpenAI' },
];

const statusMeta = {
  implemented: { color: 'green', label: '已接入' },
  pending_adapter: { color: 'orange', label: '待接入价格源' },
  ok: { color: 'green', label: '健康' },
  stale: { color: 'orange', label: '价格过期' },
  no_snapshot: { color: 'yellow', label: '无快照' },
  normal: { color: 'green', label: '正常' },
  warning: { color: 'orange', label: '警告' },
  abnormal: { color: 'red', label: '异常' },
  critical: { color: 'red', label: '严重' },
  missing: { color: 'yellow', label: '缺字段' },
  unsupported: { color: 'grey', label: '不支持' },
  out_of_scope: { color: 'blue', label: '范围外' },
  failed: { color: 'red', label: '失败' },
  exact: { color: 'green', label: 'exact' },
  standard: { color: 'teal', label: 'standard' },
  estimated: { color: 'blue', label: 'estimated' },
  open: { color: 'grey', label: 'open' },
  acknowledged: { color: 'blue', label: 'acknowledged' },
  ignored: { color: 'grey', label: 'ignored' },
  resolved: { color: 'green', label: 'resolved' },
};

const formatTime = (value) => {
  if (!value) return '-';
  return new Date(Number(value) * 1000).toLocaleString();
};

const formatDuration = (seconds) => {
  const value = Number(seconds || 0);
  if (!value) return '-';
  const hours = value / 3600;
  if (hours < 48) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
};

const formatUSD = (value) => {
  if (value === undefined || value === null) return '-';
  return `$${Number(value).toFixed(8)}`;
};

const formatPrice = (value) => {
  if (value === undefined || value === null || Number(value) === 0) return '-';
  return Number(value).toPrecision(8);
};

const formatPercent = (value) => {
  if (value === undefined || value === null) return '-';
  return `${(Number(value) * 100).toFixed(3)}%`;
};

const TagValue = ({ value }) => {
  const meta = statusMeta[value] || { color: 'grey', label: value || '-' };
  return (
    <Tag color={meta.color} size='small'>
      {meta.label}
    </Tag>
  );
};

const PriceInspectionPage = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const [sourceProvider, setSourceProvider] = useState('openrouter');

  const [sources, setSources] = useState([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [fetchingProvider, setFetchingProvider] = useState('');

  const [snapshots, setSnapshots] = useState([]);
  const [snapshotsTotal, setSnapshotsTotal] = useState(0);
  const [snapshotsPage, setSnapshotsPage] = useState(1);
  const [snapshotsPageSize, setSnapshotsPageSize] = useState(20);
  const [snapshotsLoading, setSnapshotsLoading] = useState(false);
  const [snapshotSaving, setSnapshotSaving] = useState(false);
  const [snapshotBatchText, setSnapshotBatchText] = useState('');
  const [snapshotBatchSaving, setSnapshotBatchSaving] = useState(false);
  const [deletingSnapshotId, setDeletingSnapshotId] = useState(0);
  const [snapshotFilters, setSnapshotFilters] = useState({
    model_id: '',
    local_model_name: '',
  });
  const [snapshotForm, setSnapshotForm] = useState({
    model_id: '',
    canonical_model_id: '',
    local_model_name: '',
    scenario: 'text_token',
    pricing_scheme: 'per_token',
    input_price_per_token: undefined,
    output_price_per_token: undefined,
    cache_read_price_per_token: undefined,
    cache_write_price_per_token: undefined,
    cache_write_5m_price_per_token: undefined,
    cache_write_1h_price_per_token: undefined,
    input_image_price_per_token: undefined,
    output_image_price_per_token: undefined,
    input_audio_price_per_token: undefined,
    output_audio_price_per_token: undefined,
    image_price: undefined,
    request_price: undefined,
  });

  const [coverageSummary, setCoverageSummary] = useState(null);
  const [coverageRows, setCoverageRows] = useState([]);
  const [coverageGeneratedAt, setCoverageGeneratedAt] = useState(0);
  const [coverageTotal, setCoverageTotal] = useState(0);
  const [coveragePage, setCoveragePage] = useState(1);
  const [coveragePageSize, setCoveragePageSize] = useState(20);
  const [coverageLoading, setCoverageLoading] = useState(false);
  const [coverageFilters, setCoverageFilters] = useState({
    support_level: '',
    reason_code: '',
    model_name: '',
  });

  const [runs, setRuns] = useState([]);
  const [runsTotal, setRunsTotal] = useState(0);
  const [runsPage, setRunsPage] = useState(1);
  const [runsPageSize, setRunsPageSize] = useState(20);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runForm, setRunForm] = useState({
    source_provider: 'openrouter',
    channel_id: undefined,
    channel_type: undefined,
    model_name: '',
    limit: 1000,
  });
  const [runningInspection, setRunningInspection] = useState(false);

  const [items, setItems] = useState([]);
  const [itemsTotal, setItemsTotal] = useState(0);
  const [itemsPage, setItemsPage] = useState(1);
  const [itemsPageSize, setItemsPageSize] = useState(20);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [itemFilters, setItemFilters] = useState({
    status: '',
    support_level: '',
    reason_code: '',
    model_name: '',
    min_diff_rate: undefined,
  });

  const [issues, setIssues] = useState([]);
  const [issuesTotal, setIssuesTotal] = useState(0);
  const [issuesPage, setIssuesPage] = useState(1);
  const [issuesPageSize, setIssuesPageSize] = useState(20);
  const [issuesLoading, setIssuesLoading] = useState(false);
  const [resolvingIssueKey, setResolvingIssueKey] = useState('');
  const [issueFilters, setIssueFilters] = useState({
    status: '',
    support_level: '',
    resolution_status: 'active',
    reason_code: '',
    model_name: '',
    min_diff_rate: undefined,
  });

  const [mappings, setMappings] = useState([]);
  const [mappingsTotal, setMappingsTotal] = useState(0);
  const [mappingsPage, setMappingsPage] = useState(1);
  const [mappingsPageSize, setMappingsPageSize] = useState(20);
  const [mappingsLoading, setMappingsLoading] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [suggesting, setSuggesting] = useState(false);
  const [creatingMappingKey, setCreatingMappingKey] = useState('');

  const supportOptions = useMemo(
    () => [
      { value: '', label: '全部可信度' },
      { value: 'exact', label: 'exact' },
      { value: 'standard', label: 'standard' },
      { value: 'estimated', label: 'estimated' },
      { value: 'unsupported', label: 'unsupported' },
      { value: 'out_of_scope', label: 'out_of_scope' },
    ],
    [],
  );

  const statusOptions = useMemo(
    () => [
      { value: '', label: '全部状态' },
      { value: 'normal', label: '正常' },
      { value: 'warning', label: '警告' },
      { value: 'abnormal', label: '异常' },
      { value: 'critical', label: '严重' },
      { value: 'missing', label: '缺字段' },
      { value: 'unsupported', label: '不支持' },
      { value: 'out_of_scope', label: '范围外' },
      { value: 'failed', label: '失败' },
    ],
    [],
  );

  const resolutionOptions = useMemo(
    () => [
      { value: 'active', label: 'active' },
      { value: 'open', label: 'open' },
      { value: 'acknowledged', label: 'acknowledged' },
      { value: 'ignored', label: 'ignored' },
      { value: 'resolved', label: 'resolved' },
      { value: 'all', label: 'all' },
    ],
    [],
  );

  const scenarioOptions = useMemo(
    () => [
      { value: 'text_token', label: 'text_token' },
      { value: 'vision_input', label: 'vision_input' },
      { value: 'image_generation', label: 'image_generation' },
      { value: 'image_edit', label: 'image_edit' },
      { value: 'tool_call', label: 'tool_call' },
      { value: 'audio', label: 'audio' },
    ],
    [],
  );

  const pricingSchemeOptions = useMemo(
    () => [
      { value: 'per_token', label: 'per_token' },
      { value: 'per_image', label: 'per_image' },
      { value: 'per_request', label: 'per_request' },
      { value: 'per_second', label: 'per_second' },
      { value: 'tiered', label: 'tiered' },
      { value: 'custom', label: 'custom' },
    ],
    [],
  );

  const loadSources = useCallback(async () => {
    setSourcesLoading(true);
    try {
      const res = await API.get('/api/price_inspection/sources');
      if (res.data.success) {
        setSources(res.data.data?.sources || []);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setSourcesLoading(false);
    }
  }, []);

  const loadSnapshots = useCallback(async () => {
    setSnapshotsLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('source_provider', sourceProvider);
      params.set('p', snapshotsPage);
      params.set('page_size', snapshotsPageSize);
      Object.entries(snapshotFilters).forEach(([key, value]) => {
        if (value !== '' && value !== undefined && value !== null) {
          params.set(key, value);
        }
      });
      const res = await API.get(
        `/api/price_inspection/snapshots?${params.toString()}`,
      );
      if (res.data.success) {
        setSnapshots(res.data.data?.items || []);
        setSnapshotsTotal(res.data.data?.total || 0);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setSnapshotsLoading(false);
    }
  }, [snapshotFilters, snapshotsPage, snapshotsPageSize, sourceProvider]);

  const loadCoverage = useCallback(async () => {
    setCoverageLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('source_provider', sourceProvider);
      params.set('p', coveragePage);
      params.set('page_size', coveragePageSize);
      Object.entries(coverageFilters).forEach(([key, value]) => {
        if (value !== '' && value !== undefined && value !== null) {
          params.set(key, value);
        }
      });
      const [listRes, summaryRes] = await Promise.all([
        API.get(`/api/price_inspection/coverage?${params.toString()}`),
        API.get(
          `/api/price_inspection/coverage/summary?source_provider=${sourceProvider}`,
        ),
      ]);
      if (listRes.data.success) {
        const payload = listRes.data.data || {};
        const page = payload.page || {};
        setCoverageRows(page.items || []);
        setCoverageTotal(page.total || 0);
        setCoverageGeneratedAt(payload.generated_at || 0);
      } else {
        showError(listRes.data.message);
      }
      if (summaryRes.data.success) {
        setCoverageSummary(summaryRes.data.data || null);
      } else {
        showError(summaryRes.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setCoverageLoading(false);
    }
  }, [coverageFilters, coveragePage, coveragePageSize, sourceProvider]);

  const loadRuns = useCallback(async () => {
    setRunsLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('source_provider', sourceProvider);
      params.set('p', runsPage);
      params.set('page_size', runsPageSize);
      const res = await API.get(
        `/api/price_inspection/runs?${params.toString()}`,
      );
      if (res.data.success) {
        setRuns(res.data.data?.items || []);
        setRunsTotal(res.data.data?.total || 0);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setRunsLoading(false);
    }
  }, [runsPage, runsPageSize, sourceProvider]);

  const loadItems = useCallback(async () => {
    setItemsLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('source_provider', sourceProvider);
      params.set('p', itemsPage);
      params.set('page_size', itemsPageSize);
      Object.entries(itemFilters).forEach(([key, value]) => {
        if (value !== '' && value !== undefined && value !== null) {
          params.set(key, value);
        }
      });
      const res = await API.get(
        `/api/price_inspection/items?${params.toString()}`,
      );
      if (res.data.success) {
        setItems(res.data.data?.items || []);
        setItemsTotal(res.data.data?.total || 0);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setItemsLoading(false);
    }
  }, [itemFilters, itemsPage, itemsPageSize, sourceProvider]);

  const loadIssues = useCallback(async () => {
    setIssuesLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('source_provider', sourceProvider);
      params.set('p', issuesPage);
      params.set('page_size', issuesPageSize);
      Object.entries(issueFilters).forEach(([key, value]) => {
        if (value !== '' && value !== undefined && value !== null) {
          params.set(key, value);
        }
      });
      const res = await API.get(
        `/api/price_inspection/issues?${params.toString()}`,
      );
      if (res.data.success) {
        setIssues(res.data.data?.items || []);
        setIssuesTotal(res.data.data?.total || 0);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setIssuesLoading(false);
    }
  }, [issueFilters, issuesPage, issuesPageSize, sourceProvider]);

  const loadMappings = useCallback(async () => {
    setMappingsLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('source_provider', sourceProvider);
      params.set('p', mappingsPage);
      params.set('page_size', mappingsPageSize);
      const res = await API.get(
        `/api/price_inspection/model_mappings?${params.toString()}`,
      );
      if (res.data.success) {
        setMappings(res.data.data?.items || []);
        setMappingsTotal(res.data.data?.total || 0);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setMappingsLoading(false);
    }
  }, [mappingsPage, mappingsPageSize, sourceProvider]);

  const refreshAll = useCallback(() => {
    loadSources();
    loadSnapshots();
    loadCoverage();
    loadRuns();
    loadIssues();
    loadItems();
    loadMappings();
  }, [
    loadCoverage,
    loadIssues,
    loadItems,
    loadMappings,
    loadRuns,
    loadSnapshots,
    loadSources,
  ]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  const generateCoverage = async () => {
    setCoverageLoading(true);
    try {
      const res = await API.post('/api/price_inspection/coverage/generate', {
        source_provider: sourceProvider,
        log_window_days: 30,
      });
      if (res.data.success) {
        showSuccess('覆盖率报表已生成');
        setCoveragePage(1);
        await loadCoverage();
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setCoverageLoading(false);
    }
  };

  const fetchPrices = async (provider) => {
    setFetchingProvider(provider);
    try {
      const res = await API.post(
        `/api/price_inspection/sources/${provider}/fetch`,
      );
      if (res.data.success) {
        showSuccess(`价格快照已拉取：${res.data.data.count} 条`);
        loadSources();
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setFetchingProvider('');
    }
  };

  const createSnapshot = async () => {
    setSnapshotSaving(true);
    try {
      const payload = {
        source_provider: sourceProvider,
        ...snapshotForm,
      };
      const res = await API.post('/api/price_inspection/snapshots', payload);
      if (res.data.success) {
        showSuccess('Price snapshot created');
        setSnapshotsPage(1);
        setSnapshotForm((prev) => ({
          ...prev,
          model_id: '',
          canonical_model_id: '',
          local_model_name: '',
          input_price_per_token: undefined,
          output_price_per_token: undefined,
          cache_read_price_per_token: undefined,
          cache_write_price_per_token: undefined,
          cache_write_5m_price_per_token: undefined,
          cache_write_1h_price_per_token: undefined,
          input_image_price_per_token: undefined,
          output_image_price_per_token: undefined,
          input_audio_price_per_token: undefined,
          output_audio_price_per_token: undefined,
          image_price: undefined,
          request_price: undefined,
        }));
        loadSources();
        loadSnapshots();
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setSnapshotSaving(false);
    }
  };

  const createSnapshotBatch = async () => {
    setSnapshotBatchSaving(true);
    try {
      let parsed;
      try {
        parsed = JSON.parse(snapshotBatchText);
      } catch (e) {
        showError(`Invalid JSON: ${e.message}`);
        return;
      }
      const rows = Array.isArray(parsed)
        ? parsed
        : parsed?.snapshots || parsed?.rows;
      if (!Array.isArray(rows) || rows.length === 0) {
        showError('JSON must be an array or contain snapshots');
        return;
      }
      const res = await API.post('/api/price_inspection/snapshots/batch', {
        source_provider: sourceProvider,
        snapshots: rows,
      });
      if (res.data.success) {
        showSuccess(`Imported ${res.data.data?.count || 0} snapshots`);
        setSnapshotBatchText('');
        setSnapshotsPage(1);
        loadSources();
        loadSnapshots();
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setSnapshotBatchSaving(false);
    }
  };

  const deleteSnapshot = async (record) => {
    setDeletingSnapshotId(record.id);
    try {
      const res = await API.delete(`/api/price_inspection/snapshots/${record.id}`);
      if (res.data.success) {
        showSuccess('Price snapshot deleted');
        loadSources();
        loadSnapshots();
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setDeletingSnapshotId(0);
    }
  };

  const runInspection = async () => {
    setRunningInspection(true);
    try {
      const payload = {
        source_provider: runForm.source_provider || sourceProvider,
        limit: runForm.limit || 1000,
        trigger_type: 'manual',
      };
      if (runForm.channel_id) payload.channel_id = Number(runForm.channel_id);
      if (runForm.channel_type)
        payload.channel_type = Number(runForm.channel_type);
      if (runForm.model_name) payload.model_name = runForm.model_name;
      const res = await API.post('/api/price_inspection/run', payload);
      if (res.data.success) {
        const d = res.data.data || {};
        Notification.success({
          title: '巡检完成',
          content: `run #${d.run_id}，检查 ${d.checked_logs || 0} 条，异常 ${Number(d.warning_count || 0) + Number(d.abnormal_count || 0) + Number(d.critical_count || 0)} 条`,
          duration: 5,
        });
        setSourceProvider(payload.source_provider);
        setRunsPage(1);
        setIssuesPage(1);
        setItemsPage(1);
        loadRuns();
        loadIssues();
        loadItems();
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setRunningInspection(false);
    }
  };

  const issueKey = (record) =>
    `${record.source_provider}:${record.model_name}:${record.channel_id}:${record.channel_type}:${record.status}:${record.support_level}:${record.reason_code}`;

  const updateIssueResolution = async (record, resolutionStatus) => {
    const key = issueKey(record);
    setResolvingIssueKey(`${key}:${resolutionStatus}`);
    try {
      const res = await API.put('/api/price_inspection/issues/resolution', {
        source_provider: record.source_provider,
        model_name: record.model_name,
        channel_id: record.channel_id || 0,
        channel_type: record.channel_type || 0,
        status: record.status,
        support_level: record.support_level,
        reason_code: record.reason_code,
        resolution_status: resolutionStatus,
      });
      if (res.data.success) {
        showSuccess('Issue status updated');
        loadIssues();
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setResolvingIssueKey('');
    }
  };

  const downloadPriceInspectionCsv = async (type) => {
    const params = new URLSearchParams();
    params.set('source_provider', sourceProvider);
    params.set('limit', '50000');
    const filters =
      type === 'issues'
        ? issueFilters
        : type === 'coverage'
          ? coverageFilters
          : itemFilters;
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        params.set(key, value);
      }
    });
    if (type === 'items' && selectedRunId) {
      params.set('run_id', selectedRunId);
    }
    if (type === 'coverage' && coverageGeneratedAt) {
      params.set('generated_at', coverageGeneratedAt);
    }
    try {
      const res = await API.get(
        `/api/price_inspection/${type}/export?${params.toString()}`,
        { responseType: 'blob' },
      );
      const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const disposition = res.headers['content-disposition'];
      const filename = disposition
        ? disposition.split('filename=')[1]?.replace(/"/g, '')
        : `price-inspection-${type}.csv`;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (e) {
      showError(e.message || 'CSV export failed');
    }
  };

  const suggestMappings = async () => {
    setSuggesting(true);
    try {
      const res = await API.post(
        '/api/price_inspection/model_mappings/suggest',
        {
          source_provider: sourceProvider,
          generated_at: coverageGeneratedAt,
          limit: 50,
          min_score: 0.58,
        },
      );
      if (res.data.success) {
        setSuggestions(res.data.data?.suggestions || []);
        showSuccess(`生成 ${res.data.data?.count || 0} 条映射建议`);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setSuggesting(false);
    }
  };

  const createMapping = async (row) => {
    const key = `${row.local_model_name}:${row.suggested_source_model_id}`;
    setCreatingMappingKey(key);
    try {
      const res = await API.post('/api/price_inspection/model_mappings', {
        source_provider: sourceProvider,
        channel_type: row.channel_type,
        local_model_name: row.local_model_name,
        source_model_id: row.suggested_source_model_id,
        canonical_model_id: row.suggested_source_model_id,
        scenario: row.scenario,
        confidence: row.confidence,
        enabled: true,
        note: `suggested by coverage #${row.coverage_report_id}, score=${row.score}`,
      });
      if (res.data.success) {
        showSuccess('映射已创建');
        loadMappings();
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setCreatingMappingKey('');
    }
  };

  const summaryBySupport = useMemo(() => {
    const rows = coverageSummary?.by_support || [];
    return rows.reduce((acc, row) => {
      acc[row.key || 'unknown'] = row.count;
      return acc;
    }, {});
  }, [coverageSummary]);

  const snapshotColumns = [
    {
      title: 'Model',
      dataIndex: 'model_id',
      width: 280,
      render: (_, record) => (
        <div>
          <Text strong>{record.model_id || record.local_model_name || '-'}</Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            {record.canonical_model_id || '-'} / {record.local_model_name || '-'}
          </Text>
        </div>
      ),
    },
    {
      title: 'Scenario',
      width: 180,
      render: (_, record) => (
        <Space spacing={4} wrap>
          <Tag size='small' color='blue'>
            {record.scenario || '-'}
          </Tag>
          <Tag size='small' color='grey'>
            {record.pricing_scheme || '-'}
          </Tag>
        </Space>
      ),
    },
    {
      title: 'Token Price',
      width: 220,
      render: (_, record) => (
        <div>
          <Text>in {formatPrice(record.input_price_per_token)}</Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            out {formatPrice(record.output_price_per_token)}
          </Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            cache {formatPrice(record.cache_read_price_per_token)} /{' '}
            {formatPrice(record.cache_write_price_per_token)}
          </Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            c5m {formatPrice(record.cache_write_5m_price_per_token)} / c1h{' '}
            {formatPrice(record.cache_write_1h_price_per_token)}
          </Text>
        </div>
      ),
    },
    {
      title: 'Media Price',
      width: 230,
      render: (_, record) => (
        <div>
          <Text>
            img {formatPrice(record.input_image_price_per_token)} /{' '}
            {formatPrice(record.output_image_price_per_token)}
          </Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            aud {formatPrice(record.input_audio_price_per_token)} /{' '}
            {formatPrice(record.output_audio_price_per_token)}
          </Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            image {formatPrice(record.image_price)} / req{' '}
            {formatPrice(record.request_price)}
          </Text>
        </div>
      ),
    },
    {
      title: 'Fetched',
      width: 180,
      render: (_, record) => (
        <div>
          <Text>{formatTime(record.fetched_at)}</Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            {record.currency || 'USD'} / {record.unit || '-'}
          </Text>
        </div>
      ),
    },
    {
      title: 'Type',
      width: 90,
      render: (_, record) => (
        <Tag size='small' color={record.manual ? 'orange' : 'green'}>
          {record.manual ? 'manual' : 'auto'}
        </Tag>
      ),
    },
    {
      title: 'Action',
      width: 100,
      render: (_, record) => (
        <Button
          icon={<Trash2 size={14} />}
          size='small'
          type='danger'
          theme='borderless'
          disabled={!record.manual}
          loading={deletingSnapshotId === record.id}
          onClick={() => deleteSnapshot(record)}
        />
      ),
    },
  ];

  const sourceColumns = [
    {
      title: '价格源',
      dataIndex: 'provider',
      width: 180,
      render: (_, record) => (
        <div>
          <Text strong>{record.display_name}</Text>
          <Text type='tertiary' style={{ display: 'block' }}>
            {record.provider}
          </Text>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 130,
      render: (v) => <TagValue value={v} />,
    },
    {
      title: '健康',
      dataIndex: 'health_status',
      width: 120,
      render: (v) => <TagValue value={v} />,
    },
    {
      title: '能力',
      width: 210,
      render: (_, record) => (
        <Space spacing={4} wrap>
          {record.fetch_supported ? (
            <Tag size='small' color='green'>
              fetch
            </Tag>
          ) : null}
          {record.snapshot_supported ? (
            <Tag size='small' color='blue'>
              snapshot
            </Tag>
          ) : null}
          {record.exact_log_cost_supported ? (
            <Tag size='small' color='teal'>
              exact log cost
            </Tag>
          ) : null}
          {record.standard_billing_supported ? (
            <Tag size='small' color='purple'>
              standard billing
            </Tag>
          ) : null}
        </Space>
      ),
    },
    {
      title: '快照',
      width: 170,
      render: (_, record) => (
        <div>
          <Text>{record.snapshot_count || 0} 条</Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            {formatTime(record.latest_snapshot_at)}
          </Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            age {formatDuration(record.snapshot_age_seconds)}
          </Text>
        </div>
      ),
    },
    { title: '说明', dataIndex: 'note' },
    {
      title: '操作',
      width: 120,
      render: (_, record) => (
        <Button
          icon={<Database size={14} />}
          size='small'
          disabled={!record.fetch_supported}
          loading={fetchingProvider === record.provider}
          onClick={() => fetchPrices(record.provider)}
        >
          拉价格
        </Button>
      ),
    },
  ];

  const coverageColumns = [
    {
      title: '模型',
      dataIndex: 'model_name',
      width: 260,
      render: (_, record) => (
        <div>
          <Text strong>{record.model_name}</Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            {record.channel_type_name || record.channel_type} /{' '}
            {record.scenario}
          </Text>
        </div>
      ),
    },
    {
      title: '支持级别',
      dataIndex: 'support_level',
      width: 110,
      render: (v) => <TagValue value={v} />,
    },
    { title: '映射', dataIndex: 'mapping_status', width: 150 },
    { title: '计算器', dataIndex: 'calculator_status', width: 120 },
    {
      title: '原因',
      dataIndex: 'reason_code',
      width: 210,
      render: (_, record) => (
        <div>
          <Text>{record.reason_code}</Text>
          {record.suggestion ? (
            <Text
              type='tertiary'
              size='small'
              style={{ display: 'block', wordBreak: 'break-word' }}
            >
              {record.suggestion}
            </Text>
          ) : null}
        </div>
      ),
    },
    { title: '样本', dataIndex: 'sample_log_count', width: 90 },
    {
      title: '价格模型',
      dataIndex: 'source_model_id',
      width: 240,
      render: (v) => v || '-',
    },
  ];

  const runColumns = [
    { title: 'Run', dataIndex: 'id', width: 80, render: (v) => `#${v}` },
    { title: 'Provider', dataIndex: 'source_provider', width: 130 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v) => <TagValue value={v} />,
    },
    { title: '触发', dataIndex: 'trigger_type', width: 90 },
    {
      title: '窗口',
      width: 250,
      render: (_, record) => (
        <div>
          <Text>{formatTime(record.window_start)}</Text>
          <Text type='tertiary' style={{ display: 'block' }}>
            {formatTime(record.window_end)}
          </Text>
        </div>
      ),
    },
    {
      title: '统计',
      width: 280,
      render: (_, record) => (
        <Space spacing={4} wrap>
          <Tag size='small' color='green'>
            正常 {record.normal_count}
          </Tag>
          <Tag size='small' color='orange'>
            警告 {record.warning_count}
          </Tag>
          <Tag size='small' color='red'>
            异常{' '}
            {Number(record.abnormal_count || 0) +
              Number(record.critical_count || 0)}
          </Tag>
          <Tag size='small' color='yellow'>
            缺失 {record.missing_count}
          </Tag>
          <Tag size='small' color='blue'>
            范围外 {record.out_of_scope_count}
          </Tag>
        </Space>
      ),
    },
    {
      title: '完成时间',
      dataIndex: 'finished_at',
      width: 170,
      render: formatTime,
    },
  ];

  const issueColumns = [
    {
      title: '模型 / 渠道',
      width: 280,
      render: (_, record) => (
        <div>
          <Text strong>{record.model_name || '-'}</Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            channel #{record.channel_id || '-'} / type{' '}
            {record.channel_type || '-'}
          </Text>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 105,
      render: (v) => <TagValue value={v} />,
    },
    {
      title: '级别',
      dataIndex: 'support_level',
      width: 105,
      render: (v) => <TagValue value={v} />,
    },
    { title: '原因', dataIndex: 'reason_code', width: 210 },
    { title: '次数', dataIndex: 'count', width: 80 },
    {
      title: '累计差异',
      width: 170,
      render: (_, record) => (
        <div>
          <Text type={record.total_delta_quota > 0 ? 'danger' : 'tertiary'}>
            {record.total_delta_quota}
          </Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            max {record.max_abs_delta_quota}
          </Text>
        </div>
      ),
    },
    {
      title: '最大差异率',
      dataIndex: 'max_diff_rate',
      width: 120,
      render: formatPercent,
    },
    {
      title: '样例 / 最新',
      width: 190,
      render: (_, record) => (
        <div>
          <Text>log #{record.sample_log_id || '-'}</Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            {formatTime(record.latest_log_at)}
          </Text>
        </div>
      ),
    },
    {
      title: 'Resolution',
      dataIndex: 'resolution_status',
      width: 130,
      render: (v) => <TagValue value={v || 'open'} />,
    },
    {
      title: 'Action',
      width: 220,
      fixed: 'right',
      render: (_, record) => {
        const key = issueKey(record);
        const current = record.resolution_status || 'open';
        return (
          <Space spacing={4} wrap>
            <Button
              size='small'
              disabled={current === 'acknowledged'}
              loading={resolvingIssueKey === `${key}:acknowledged`}
              onClick={() => updateIssueResolution(record, 'acknowledged')}
            >
              Ack
            </Button>
            <Button
              size='small'
              disabled={current === 'ignored'}
              loading={resolvingIssueKey === `${key}:ignored`}
              onClick={() => updateIssueResolution(record, 'ignored')}
            >
              Ignore
            </Button>
            <Button
              size='small'
              disabled={current === 'open'}
              loading={resolvingIssueKey === `${key}:open`}
              onClick={() => updateIssueResolution(record, 'open')}
            >
              Open
            </Button>
          </Space>
        );
      },
    },
  ];

  const itemColumns = [
    { title: 'Log', dataIndex: 'log_id', width: 90, render: (v) => `#${v}` },
    {
      title: '模型',
      width: 260,
      render: (_, record) => (
        <div>
          <Text strong>{record.model_name}</Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            {record.source_model_id || '-'} / {record.scenario || '-'}
          </Text>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 105,
      render: (v) => <TagValue value={v} />,
    },
    {
      title: '级别',
      dataIndex: 'support_level',
      width: 100,
      render: (v) => <TagValue value={v} />,
    },
    {
      title: 'Quota',
      width: 190,
      render: (_, record) => (
        <div>
          <Text>actual {record.actual_quota}</Text>
          <Text type='tertiary' style={{ display: 'block' }}>
            expected {record.expected_quota}
          </Text>
          <Text
            type={record.delta_quota > 0 ? 'danger' : 'tertiary'}
            style={{ display: 'block' }}
          >
            delta {record.delta_quota}
          </Text>
        </div>
      ),
    },
    {
      title: 'USD / 差异',
      width: 170,
      render: (_, record) => (
        <div>
          <Text>{formatUSD(record.actual_usd)}</Text>
          <Text type='tertiary' style={{ display: 'block' }}>
            {formatPercent(record.diff_rate)}
          </Text>
        </div>
      ),
    },
    { title: '原因', dataIndex: 'reason_code', width: 190 },
    { title: '时间', dataIndex: 'created_at', width: 170, render: formatTime },
  ];

  const mappingColumns = [
    {
      title: '本地模型',
      dataIndex: 'local_model_name',
      width: 260,
      render: (_, record) => (
        <div>
          <Text strong>{record.local_model_name}</Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            channel_type {record.channel_type || 'all'} / channel{' '}
            {record.channel_id || 'all'}
          </Text>
        </div>
      ),
    },
    { title: '价格源模型', dataIndex: 'source_model_id', width: 260 },
    { title: 'Provider', dataIndex: 'source_provider', width: 110 },
    { title: '场景', dataIndex: 'scenario', width: 130 },
    { title: '置信度', dataIndex: 'confidence', width: 110 },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 80,
      render: (v) => (v ? <Tag color='green'>是</Tag> : <Tag>否</Tag>),
    },
    { title: '备注', dataIndex: 'note' },
  ];

  const suggestionColumns = [
    {
      title: '缺口模型',
      dataIndex: 'local_model_name',
      width: 260,
      render: (_, record) => (
        <div>
          <Text strong>{record.local_model_name}</Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            {record.channel_type_name || record.channel_type} / 样本{' '}
            {record.sample_log_count}
          </Text>
        </div>
      ),
    },
    {
      title: '建议价格模型',
      dataIndex: 'suggested_source_model_id',
      width: 280,
    },
    { title: '得分', dataIndex: 'score', width: 90 },
    { title: '置信度', dataIndex: 'confidence', width: 110 },
    { title: '原因', dataIndex: 'reason', width: 160 },
    {
      title: '操作',
      width: 110,
      render: (_, record) => (
        <Button
          icon={<IconPlus />}
          size='small'
          loading={
            creatingMappingKey ===
            `${record.local_model_name}:${record.suggested_source_model_id}`
          }
          onClick={() => createMapping(record)}
        >
          创建
        </Button>
      ),
    },
  ];

  return (
    <div className='p-4 lg:p-6' style={{ maxWidth: 1500, margin: '0 auto' }}>
      <div className='mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between'>
        <div>
          <Title heading={3} style={{ margin: 0 }}>
            价格巡检
          </Title>
          <Text type='tertiary'>
            按价格源和真实扣费上下文检查 logs.quota，独立于对账模块。
          </Text>
        </div>
        <Space wrap>
          <Select
            optionList={PROVIDER_OPTIONS}
            value={sourceProvider}
            style={{ width: 190 }}
            onChange={(value) => {
              setSourceProvider(value);
              setCoveragePage(1);
              setSnapshotsPage(1);
              setRunsPage(1);
              setIssuesPage(1);
              setItemsPage(1);
              setMappingsPage(1);
            }}
          />
          <Button icon={<IconRefresh />} onClick={refreshAll}>
            刷新
          </Button>
        </Space>
      </div>

      <Banner
        className='mb-4'
        type='info'
        description='文生文和带 provider_usage_cost 的新日志可进入 exact 巡检；可灵、Vidu、Sora、DoubaoVideo 等视频/任务型模型会标记为 out_of_scope。'
      />

      <Tabs activeKey={activeTab} onChange={setActiveTab} type='line'>
        <Tabs.TabPane tab='概览' itemKey='overview'>
          <Space vertical align='start' style={{ width: '100%' }}>
            <div className='grid w-full grid-cols-1 gap-3 md:grid-cols-4'>
              <Card>
                <Text type='tertiary'>覆盖模型</Text>
                <Title heading={4}>{coverageSummary?.total || 0}</Title>
              </Card>
              <Card>
                <Text type='tertiary'>exact / standard</Text>
                <Title heading={4}>
                  {Number(summaryBySupport.exact || 0) +
                    Number(summaryBySupport.standard || 0)}
                </Title>
              </Card>
              <Card>
                <Text type='tertiary'>unsupported</Text>
                <Title heading={4}>{summaryBySupport.unsupported || 0}</Title>
              </Card>
              <Card>
                <Text type='tertiary'>out_of_scope</Text>
                <Title heading={4}>{summaryBySupport.out_of_scope || 0}</Title>
              </Card>
            </div>
            <Card style={{ width: '100%' }}>
              <div className='mb-3 flex items-center justify-between gap-3'>
                <Title heading={5} style={{ margin: 0 }}>
                  价格源
                </Title>
                <Button
                  icon={<IconRefresh />}
                  loading={sourcesLoading}
                  onClick={loadSources}
                >
                  刷新价格源
                </Button>
              </div>
              <Table
                rowKey='provider'
                columns={sourceColumns}
                dataSource={sources}
                loading={sourcesLoading}
                pagination={false}
              />
            </Card>
          </Space>
        </Tabs.TabPane>

        <Tabs.TabPane tab='Price Snapshots' itemKey='snapshots'>
          <Space vertical align='start' style={{ width: '100%' }}>
            <Card style={{ width: '100%' }}>
              <Form layout='horizontal' labelPosition='left'>
                <Form.Input
                  field='snapshot_model_id'
                  label='Model ID'
                  value={snapshotForm.model_id}
                  style={{ width: 250 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({ ...prev, model_id: value }))
                  }
                />
                <Form.Input
                  field='snapshot_canonical_model_id'
                  label='Canonical'
                  value={snapshotForm.canonical_model_id}
                  style={{ width: 250 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({
                      ...prev,
                      canonical_model_id: value,
                    }))
                  }
                />
                <Form.Input
                  field='snapshot_local_model_name'
                  label='Local Name'
                  value={snapshotForm.local_model_name}
                  style={{ width: 250 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({
                      ...prev,
                      local_model_name: value,
                    }))
                  }
                />
                <Form.Select
                  field='snapshot_scenario'
                  label='Scenario'
                  optionList={scenarioOptions}
                  value={snapshotForm.scenario}
                  style={{ width: 190 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({ ...prev, scenario: value }))
                  }
                />
                <Form.Select
                  field='snapshot_pricing_scheme'
                  label='Scheme'
                  optionList={pricingSchemeOptions}
                  value={snapshotForm.pricing_scheme}
                  style={{ width: 170 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({
                      ...prev,
                      pricing_scheme: value,
                    }))
                  }
                />
                <Form.InputNumber
                  field='snapshot_input_price'
                  label='Input/token'
                  value={snapshotForm.input_price_per_token}
                  step={0.000000001}
                  style={{ width: 160 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({
                      ...prev,
                      input_price_per_token: value,
                    }))
                  }
                />
                <Form.InputNumber
                  field='snapshot_output_price'
                  label='Output/token'
                  value={snapshotForm.output_price_per_token}
                  step={0.000000001}
                  style={{ width: 160 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({
                      ...prev,
                      output_price_per_token: value,
                    }))
                  }
                />
                <Form.InputNumber
                  field='snapshot_cache_read_price'
                  label='Cache read'
                  value={snapshotForm.cache_read_price_per_token}
                  step={0.000000001}
                  style={{ width: 150 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({
                      ...prev,
                      cache_read_price_per_token: value,
                    }))
                  }
                />
                <Form.InputNumber
                  field='snapshot_cache_write_price'
                  label='Cache write'
                  value={snapshotForm.cache_write_price_per_token}
                  step={0.000000001}
                  style={{ width: 150 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({
                      ...prev,
                      cache_write_price_per_token: value,
                    }))
                  }
                />
                <Form.InputNumber
                  field='snapshot_cache_write_5m_price'
                  label='Cache 5m'
                  value={snapshotForm.cache_write_5m_price_per_token}
                  step={0.000000001}
                  style={{ width: 150 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({
                      ...prev,
                      cache_write_5m_price_per_token: value,
                    }))
                  }
                />
                <Form.InputNumber
                  field='snapshot_cache_write_1h_price'
                  label='Cache 1h'
                  value={snapshotForm.cache_write_1h_price_per_token}
                  step={0.000000001}
                  style={{ width: 150 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({
                      ...prev,
                      cache_write_1h_price_per_token: value,
                    }))
                  }
                />
                <Form.InputNumber
                  field='snapshot_input_image_price'
                  label='Image in/token'
                  value={snapshotForm.input_image_price_per_token}
                  step={0.000000001}
                  style={{ width: 160 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({
                      ...prev,
                      input_image_price_per_token: value,
                    }))
                  }
                />
                <Form.InputNumber
                  field='snapshot_output_image_price'
                  label='Image out/token'
                  value={snapshotForm.output_image_price_per_token}
                  step={0.000000001}
                  style={{ width: 165 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({
                      ...prev,
                      output_image_price_per_token: value,
                    }))
                  }
                />
                <Form.InputNumber
                  field='snapshot_input_audio_price'
                  label='Audio in/token'
                  value={snapshotForm.input_audio_price_per_token}
                  step={0.000000001}
                  style={{ width: 160 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({
                      ...prev,
                      input_audio_price_per_token: value,
                    }))
                  }
                />
                <Form.InputNumber
                  field='snapshot_output_audio_price'
                  label='Audio out/token'
                  value={snapshotForm.output_audio_price_per_token}
                  step={0.000000001}
                  style={{ width: 165 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({
                      ...prev,
                      output_audio_price_per_token: value,
                    }))
                  }
                />
                <Form.InputNumber
                  field='snapshot_image_price'
                  label='Image'
                  value={snapshotForm.image_price}
                  step={0.000001}
                  style={{ width: 140 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({ ...prev, image_price: value }))
                  }
                />
                <Form.InputNumber
                  field='snapshot_request_price'
                  label='Request'
                  value={snapshotForm.request_price}
                  step={0.000001}
                  style={{ width: 140 }}
                  onChange={(value) =>
                    setSnapshotForm((prev) => ({
                      ...prev,
                      request_price: value,
                    }))
                  }
                />
                <Button
                  icon={<IconPlus />}
                  loading={snapshotSaving}
                  onClick={createSnapshot}
                >
                  Create
                </Button>
              </Form>
            </Card>
            <Card style={{ width: '100%' }}>
              <Space vertical align='start' style={{ width: '100%' }}>
                <TextArea
                  value={snapshotBatchText}
                  autosize={{ minRows: 5, maxRows: 10 }}
                  placeholder='[{"model_id":"gemini-2.5-flash-image","local_model_name":"gemini-2.5-flash-image","scenario":"image_generation","input_image_price_per_token":0.000001,"output_image_price_per_token":0.000002,"image_price":0.000039}]'
                  onChange={setSnapshotBatchText}
                />
                <Button
                  icon={<IconPlus />}
                  loading={snapshotBatchSaving}
                  disabled={!snapshotBatchText.trim()}
                  onClick={createSnapshotBatch}
                >
                  Import JSON
                </Button>
              </Space>
            </Card>
            <Card style={{ width: '100%' }}>
              <div className='mb-3 flex flex-wrap gap-2'>
                <Input
                  prefix={<IconSearch />}
                  placeholder='model_id'
                  value={snapshotFilters.model_id}
                  style={{ width: 240 }}
                  onChange={(value) =>
                    setSnapshotFilters((prev) => ({ ...prev, model_id: value }))
                  }
                  onEnterPress={() => {
                    setSnapshotsPage(1);
                    loadSnapshots();
                  }}
                />
                <Input
                  prefix={<IconSearch />}
                  placeholder='local_model_name'
                  value={snapshotFilters.local_model_name}
                  style={{ width: 240 }}
                  onChange={(value) =>
                    setSnapshotFilters((prev) => ({
                      ...prev,
                      local_model_name: value,
                    }))
                  }
                  onEnterPress={() => {
                    setSnapshotsPage(1);
                    loadSnapshots();
                  }}
                />
                <Button
                  icon={<IconRefresh />}
                  loading={snapshotsLoading}
                  onClick={loadSnapshots}
                >
                  Refresh
                </Button>
              </div>
              <Table
                rowKey={(record) =>
                  `${record.source_provider}:${record.id}:${record.fetched_at}`
                }
                columns={snapshotColumns}
                dataSource={snapshots}
                loading={snapshotsLoading}
                pagination={{
                  currentPage: snapshotsPage,
                  pageSize: snapshotsPageSize,
                  total: snapshotsTotal,
                  showSizeChanger: true,
                  onPageChange: setSnapshotsPage,
                  onPageSizeChange: (size) => {
                    setSnapshotsPageSize(size);
                    setSnapshotsPage(1);
                  },
                }}
              />
            </Card>
          </Space>
        </Tabs.TabPane>

        <Tabs.TabPane tab='覆盖率' itemKey='coverage'>
          <Card>
            <div className='mb-3 flex flex-wrap items-end gap-2'>
              <Select
                optionList={supportOptions}
                value={coverageFilters.support_level}
                style={{ width: 170 }}
                onChange={(value) => {
                  setCoverageFilters((prev) => ({
                    ...prev,
                    support_level: value,
                  }));
                  setCoveragePage(1);
                }}
              />
              <Input
                prefix={<IconSearch />}
                placeholder='模型名'
                value={coverageFilters.model_name}
                style={{ width: 220 }}
                onChange={(value) =>
                  setCoverageFilters((prev) => ({ ...prev, model_name: value }))
                }
                onEnterPress={() => {
                  setCoveragePage(1);
                  loadCoverage();
                }}
              />
              <Input
                placeholder='reason_code'
                value={coverageFilters.reason_code}
                style={{ width: 220 }}
                onChange={(value) =>
                  setCoverageFilters((prev) => ({
                    ...prev,
                    reason_code: value,
                  }))
                }
                onEnterPress={() => {
                  setCoveragePage(1);
                  loadCoverage();
                }}
              />
              <Button
                icon={<Sparkles size={14} />}
                loading={coverageLoading}
                onClick={generateCoverage}
              >
                生成覆盖率
              </Button>
              <Button
                icon={<IconRefresh />}
                loading={coverageLoading}
                onClick={loadCoverage}
              >
                查询
              </Button>
              <Button
                icon={<Download size={14} />}
                disabled={!coverageGeneratedAt}
                onClick={() => downloadPriceInspectionCsv('coverage')}
              >
                导出
              </Button>
              <Text type='tertiary'>
                最新生成：{formatTime(coverageGeneratedAt)}
              </Text>
            </div>
            <Table
              rowKey='id'
              columns={coverageColumns}
              dataSource={coverageRows}
              loading={coverageLoading}
              pagination={{
                currentPage: coveragePage,
                pageSize: coveragePageSize,
                total: coverageTotal,
                showSizeChanger: true,
                onPageChange: setCoveragePage,
                onPageSizeChange: (size) => {
                  setCoveragePageSize(size);
                  setCoveragePage(1);
                },
              }}
            />
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane tab='巡检运行' itemKey='runs'>
          <Space vertical align='start' style={{ width: '100%' }}>
            <Card style={{ width: '100%' }}>
              <Form layout='horizontal' labelPosition='left'>
                <Form.Select
                  field='source_provider'
                  label='Provider'
                  optionList={PROVIDER_OPTIONS}
                  value={runForm.source_provider}
                  style={{ width: 210 }}
                  onChange={(value) =>
                    setRunForm((prev) => ({ ...prev, source_provider: value }))
                  }
                />
                <Form.InputNumber
                  field='channel_id'
                  label='渠道 ID'
                  value={runForm.channel_id}
                  style={{ width: 150 }}
                  onChange={(value) =>
                    setRunForm((prev) => ({ ...prev, channel_id: value }))
                  }
                />
                <Form.InputNumber
                  field='channel_type'
                  label='渠道类型'
                  value={runForm.channel_type}
                  style={{ width: 150 }}
                  onChange={(value) =>
                    setRunForm((prev) => ({ ...prev, channel_type: value }))
                  }
                />
                <Form.Input
                  field='model_name'
                  label='模型'
                  value={runForm.model_name}
                  style={{ width: 240 }}
                  onChange={(value) =>
                    setRunForm((prev) => ({ ...prev, model_name: value }))
                  }
                />
                <Form.InputNumber
                  field='limit'
                  label='Limit'
                  value={runForm.limit}
                  style={{ width: 150 }}
                  onChange={(value) =>
                    setRunForm((prev) => ({ ...prev, limit: value }))
                  }
                />
                <Button
                  icon={<Play size={14} />}
                  loading={runningInspection}
                  onClick={runInspection}
                >
                  运行巡检
                </Button>
              </Form>
            </Card>
            <Card style={{ width: '100%' }}>
              <div className='mb-3 flex justify-between'>
                <Title heading={5} style={{ margin: 0 }}>
                  运行记录
                </Title>
                <Button
                  icon={<IconRefresh />}
                  loading={runsLoading}
                  onClick={loadRuns}
                >
                  刷新
                </Button>
              </div>
              <Table
                rowKey='id'
                columns={runColumns}
                dataSource={runs}
                loading={runsLoading}
                pagination={{
                  currentPage: runsPage,
                  pageSize: runsPageSize,
                  total: runsTotal,
                  showSizeChanger: true,
                  onPageChange: setRunsPage,
                  onPageSizeChange: (size) => {
                    setRunsPageSize(size);
                    setRunsPage(1);
                  },
                }}
              />
            </Card>
          </Space>
        </Tabs.TabPane>

        <Tabs.TabPane tab='问题聚合' itemKey='issues'>
          <Card>
            <div className='mb-3 flex flex-wrap gap-2'>
              <Select
                optionList={statusOptions}
                value={issueFilters.status}
                style={{ width: 150 }}
                onChange={(value) => {
                  setIssueFilters((prev) => ({ ...prev, status: value }));
                  setIssuesPage(1);
                }}
              />
              <Select
                optionList={supportOptions}
                value={issueFilters.support_level}
                style={{ width: 165 }}
                onChange={(value) => {
                  setIssueFilters((prev) => ({
                    ...prev,
                    support_level: value,
                  }));
                  setIssuesPage(1);
                }}
              />
              <Select
                optionList={resolutionOptions}
                value={issueFilters.resolution_status}
                style={{ width: 165 }}
                onChange={(value) => {
                  setIssueFilters((prev) => ({
                    ...prev,
                    resolution_status: value,
                  }));
                  setIssuesPage(1);
                }}
              />
              <Input
                prefix={<IconSearch />}
                placeholder='模型名'
                value={issueFilters.model_name}
                style={{ width: 220 }}
                onChange={(value) =>
                  setIssueFilters((prev) => ({ ...prev, model_name: value }))
                }
              />
              <Input
                placeholder='reason_code'
                value={issueFilters.reason_code}
                style={{ width: 220 }}
                onChange={(value) =>
                  setIssueFilters((prev) => ({ ...prev, reason_code: value }))
                }
              />
              <InputNumber
                placeholder='最小差异率'
                value={issueFilters.min_diff_rate}
                step={0.001}
                style={{ width: 150 }}
                onChange={(value) =>
                  setIssueFilters((prev) => ({
                    ...prev,
                    min_diff_rate: value,
                  }))
                }
              />
              <Button
                icon={<IconRefresh />}
                loading={issuesLoading}
                onClick={loadIssues}
              >
                查询
              </Button>
              <Text type='tertiary'>
                默认聚合 warning / abnormal / critical / missing / failed，排除
                unsupported 和 out_of_scope。
              </Text>
            </div>
            <div className='mb-3'>
              <Button
                icon={<Download size={14} />}
                onClick={() => downloadPriceInspectionCsv('issues')}
              >
                CSV
              </Button>
            </div>
            <Table
              rowKey={issueKey}
              columns={issueColumns}
              dataSource={issues}
              loading={issuesLoading}
              pagination={{
                currentPage: issuesPage,
                pageSize: issuesPageSize,
                total: issuesTotal,
                showSizeChanger: true,
                onPageChange: setIssuesPage,
                onPageSizeChange: (size) => {
                  setIssuesPageSize(size);
                  setIssuesPage(1);
                },
              }}
            />
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane tab='异常明细' itemKey='items'>
          <Card>
            <div className='mb-3 flex flex-wrap gap-2'>
              <Select
                optionList={statusOptions}
                value={itemFilters.status}
                style={{ width: 150 }}
                onChange={(value) => {
                  setItemFilters((prev) => ({ ...prev, status: value }));
                  setItemsPage(1);
                }}
              />
              <Select
                optionList={supportOptions}
                value={itemFilters.support_level}
                style={{ width: 165 }}
                onChange={(value) => {
                  setItemFilters((prev) => ({ ...prev, support_level: value }));
                  setItemsPage(1);
                }}
              />
              <Input
                prefix={<IconSearch />}
                placeholder='模型名'
                value={itemFilters.model_name}
                style={{ width: 220 }}
                onChange={(value) =>
                  setItemFilters((prev) => ({ ...prev, model_name: value }))
                }
              />
              <Input
                placeholder='reason_code'
                value={itemFilters.reason_code}
                style={{ width: 220 }}
                onChange={(value) =>
                  setItemFilters((prev) => ({ ...prev, reason_code: value }))
                }
              />
              <InputNumber
                placeholder='最小差异率'
                value={itemFilters.min_diff_rate}
                step={0.001}
                style={{ width: 150 }}
                onChange={(value) =>
                  setItemFilters((prev) => ({ ...prev, min_diff_rate: value }))
                }
              />
              <Button
                icon={<IconRefresh />}
                loading={itemsLoading}
                onClick={loadItems}
              >
                查询
              </Button>
            </div>
            <div className='mb-3'>
              <Button
                icon={<Download size={14} />}
                onClick={() => downloadPriceInspectionCsv('items')}
              >
                CSV
              </Button>
            </div>
            <Table
              rowKey='id'
              columns={itemColumns}
              dataSource={items}
              loading={itemsLoading}
              pagination={{
                currentPage: itemsPage,
                pageSize: itemsPageSize,
                total: itemsTotal,
                showSizeChanger: true,
                onPageChange: setItemsPage,
                onPageSizeChange: (size) => {
                  setItemsPageSize(size);
                  setItemsPage(1);
                },
              }}
            />
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane tab='模型映射' itemKey='mappings'>
          <Space vertical align='start' style={{ width: '100%' }}>
            <Card style={{ width: '100%' }}>
              <div className='mb-3 flex flex-wrap items-center justify-between gap-2'>
                <div>
                  <Title heading={5} style={{ margin: 0 }}>
                    映射建议
                  </Title>
                  <Text type='tertiary'>
                    基于最新覆盖率缺口和价格快照生成，创建前需要人工确认。
                  </Text>
                </div>
                <Space>
                  <Button
                    icon={<Sparkles size={14} />}
                    loading={suggesting}
                    onClick={suggestMappings}
                  >
                    生成建议
                  </Button>
                  <Button
                    icon={<IconRefresh />}
                    loading={mappingsLoading}
                    onClick={loadMappings}
                  >
                    刷新映射
                  </Button>
                </Space>
              </div>
              <Table
                rowKey={(record) =>
                  `${record.coverage_report_id}-${record.suggested_source_model_id}`
                }
                columns={suggestionColumns}
                dataSource={suggestions}
                pagination={false}
              />
            </Card>
            <Card style={{ width: '100%' }}>
              <Title heading={5} style={{ marginTop: 0 }}>
                已配置映射
              </Title>
              <Table
                rowKey='id'
                columns={mappingColumns}
                dataSource={mappings}
                loading={mappingsLoading}
                pagination={{
                  currentPage: mappingsPage,
                  pageSize: mappingsPageSize,
                  total: mappingsTotal,
                  showSizeChanger: true,
                  onPageChange: setMappingsPage,
                  onPageSizeChange: (size) => {
                    setMappingsPageSize(size);
                    setMappingsPage(1);
                  },
                }}
              />
            </Card>
          </Space>
        </Tabs.TabPane>
      </Tabs>
    </div>
  );
};

export default PriceInspectionPage;
