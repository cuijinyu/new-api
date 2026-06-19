import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Banner,
  Button,
  Card,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  TextArea,
  Typography,
} from '@douyinfe/semi-ui';
import {
  Activity,
  RefreshCw,
  ServerCog,
  Timer,
  TrendingUp,
} from 'lucide-react';
import { VChart } from '@visactor/react-vchart';
import { initVChartSemiTheme } from '@visactor/vchart-semi-theme';
import { API, showError } from '../../helpers';

const { Text, Title } = Typography;

const CHART_CONFIG = { mode: 'desktop-browser' };
const MAX_SELECTED_CHANNELS = 8;

const hoursOptions = [
  { value: 1, label: '?? 1 ??' },
  { value: 3, label: '?? 3 ??' },
  { value: 6, label: '?? 6 ??' },
  { value: 12, label: '?? 12 ??' },
  { value: 24, label: '?? 24 ??' },
  { value: 72, label: '?? 3 ?' },
  { value: 168, label: '?? 7 ?' },
];

const periodOptions = [
  { value: 0, label: '????' },
  { value: 60, label: '1 ??' },
  { value: 300, label: '5 ??' },
  { value: 900, label: '15 ??' },
  { value: 3600, label: '1 ??' },
];

const channelLimitOptions = [
  { value: 50, label: '50 ???' },
  { value: 120, label: '120 ???' },
  { value: 300, label: '300 ???' },
  { value: 500, label: '500 ???' },
];

const channelMetricOptions = [
  { value: 'requests', label: '???', field: 'requests', digits: 0 },
  { value: 'rpm', label: 'RPM', field: 'rpm', digits: 2 },
  {
    value: 'provider_tokens',
    label: '???? Token',
    field: 'provider_tokens',
    digits: 0,
  },
  {
    value: 'provider_tpm',
    label: '???? TPM',
    field: 'provider_tpm',
    digits: 2,
  },
  { value: 'tokens', label: '?? Token', field: 'tokens', digits: 0 },
  { value: 'tpm', label: '?? TPM', field: 'tpm', digits: 2 },
  {
    value: 'cached_tokens',
    label: 'Cache Read',
    field: 'cached_tokens',
    digits: 0,
  },
  {
    value: 'cache_creation_tokens',
    label: 'Cache Write',
    field: 'cache_creation_tokens',
    digits: 0,
  },
  {
    value: 'reasoning_tokens',
    label: 'Reasoning',
    field: 'reasoning_tokens',
    digits: 0,
  },
  {
    value: 'success_rate',
    label: '???',
    field: 'success_rate',
    digits: 2,
    suffix: '%',
  },
  {
    value: 'avg_latency_ms',
    label: '????',
    field: 'avg_latency_ms',
    digits: 0,
    suffix: ' ms',
  },
  {
    value: 'latency_p99_ms',
    label: '?? P99',
    field: 'latency_p99_ms',
    digits: 0,
    suffix: ' ms',
  },
  {
    value: 'avg_ttft_ms',
    label: '? Token',
    field: 'avg_ttft_ms',
    digits: 0,
    suffix: ' ms',
  },
  {
    value: 'ttft_p99_ms',
    label: '? Token P99',
    field: 'ttft_p99_ms',
    digits: 0,
    suffix: ' ms',
  },
  {
    value: 'upstream_latency_ms',
    label: '????',
    field: 'upstream_latency_ms',
    digits: 0,
    suffix: ' ms',
  },
  {
    value: 'upstream_p99_ms',
    label: '?? P99',
    field: 'upstream_p99_ms',
    digits: 0,
    suffix: ' ms',
  },
  { value: 'errors', label: '???', field: 'errors', digits: 0 },
  {
    value: 'upstream_errors',
    label: '????',
    field: 'upstream_errors',
    digits: 0,
  },
  { value: 'timeouts', label: '???', field: 'timeouts', digits: 0 },
  { value: 'fallbacks', label: 'Fallback', field: 'fallbacks', digits: 0 },
];

const logLimitOptions = [
  { value: 50, label: '50 ?' },
  { value: 100, label: '100 ?' },
  { value: 200, label: '200 ?' },
  { value: 500, label: '500 ?' },
];

const defaultLogQuery =
  'fields @timestamp, @logStream, @message | sort @timestamp desc | limit 100';

function formatNumber(value, digits = 0) {
  const n = Number(value || 0);
  return n.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function formatTime(ts) {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleString();
}

function channelLabel(channel) {
  if (!channel) return '-';
  return `#${channel.id} ${channel.name || channel.monitor_key}`;
}

function statusTag(status, statusText) {
  if (status === 1) {
    return <Tag color='green'>??</Tag>;
  }
  if (status === 2) {
    return <Tag color='grey'>????</Tag>;
  }
  if (status === 3) {
    return <Tag color='red'>????</Tag>;
  }
  return <Tag>{statusText || 'unknown'}</Tag>;
}

function StatCard({ icon, title, value, sub }) {
  return (
    <Card bodyStyle={{ padding: 16 }}>
      <div className='flex items-start justify-between gap-3'>
        <div>
          <Text type='tertiary' size='small'>
            {title}
          </Text>
          <div className='text-2xl font-semibold mt-1'>{value}</div>
          {sub ? (
            <Text type='tertiary' size='small'>
              {sub}
            </Text>
          ) : null}
        </div>
        <div
          className='flex items-center justify-center'
          style={{
            width: 34,
            height: 34,
            borderRadius: 6,
            background: 'var(--semi-color-fill-0)',
            color: 'var(--semi-color-primary)',
          }}
        >
          {icon}
        </div>
      </div>
    </Card>
  );
}

export default function AWSMonitoringPage() {
  const [hours, setHours] = useState(24);
  const [period, setPeriod] = useState(0);
  const [channelLimit, setChannelLimit] = useState(120);
  const [selectedChannelIds, setSelectedChannelIds] = useState([]);
  const [channelMetric, setChannelMetric] = useState('provider_tpm');
  const [logHours, setLogHours] = useState(1);
  const [logLimit, setLogLimit] = useState(100);
  const [logQuery, setLogQuery] = useState(defaultLogQuery);
  const [logLoading, setLogLoading] = useState(false);
  const [logData, setLogData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);

  useEffect(() => {
    initVChartSemiTheme({ isWatchingThemeSwitch: true });
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('hours', String(hours));
      if (period > 0) {
        params.set('period', String(period));
      }
      params.set('channel_limit', String(channelLimit));
      const res = await API.get(
        `/api/aws_monitoring/overview?${params.toString()}`,
        {
          disableDuplicate: true,
        },
      );
      if (res.data.success) {
        setData(res.data.data);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setLoading(false);
    }
  }, [hours, period, channelLimit]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const loadLogs = useCallback(async () => {
    setLogLoading(true);
    try {
      const res = await API.post(
        '/api/aws_monitoring/logs/query',
        {
          hours: logHours,
          limit: logLimit,
          query: logQuery,
        },
        {
          disableDuplicate: true,
        },
      );
      if (res.data.success) {
        setLogData(res.data.data);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setLogLoading(false);
    }
  }, [logHours, logLimit, logQuery]);

  useEffect(() => {
    const channels = data?.channels || [];
    if (!channels.length) {
      setSelectedChannelIds([]);
      return;
    }
    const validIds = new Set(channels.map((channel) => channel.id));
    setSelectedChannelIds((prev) => {
      const stillValid = prev.filter((id) => validIds.has(id));
      if (stillValid.length > 0) {
        return stillValid.slice(0, MAX_SELECTED_CHANNELS);
      }
      return channels
        .filter((channel) => channel.requests > 0)
        .slice(0, 5)
        .map((channel) => channel.id);
    });
  }, [data]);

  const selectedMetricOption = useMemo(
    () =>
      channelMetricOptions.find((option) => option.value === channelMetric) ||
      channelMetricOptions[0],
    [channelMetric],
  );

  const trafficValues = useMemo(() => {
    return (data?.series || []).flatMap((point) => [
      { time: formatTime(point.time), metric: 'RPM', value: point.rpm || 0 },
      {
        time: formatTime(point.time),
        metric: '???? TPM',
        value: point.provider_tpm || 0,
      },
    ]);
  }, [data]);

  const healthValues = useMemo(() => {
    return (data?.series || []).flatMap((point) => [
      {
        time: formatTime(point.time),
        metric: '???',
        value: point.success_rate || 0,
      },
      {
        time: formatTime(point.time),
        metric: '?? ms',
        value: point.latency_ms || 0,
      },
      {
        time: formatTime(point.time),
        metric: 'P99 ms',
        value: point.latency_p99_ms || 0,
      },
      {
        time: formatTime(point.time),
        metric: '? Token ms',
        value: point.ttft_ms || 0,
      },
      {
        time: formatTime(point.time),
        metric: '? Token P99 ms',
        value: point.ttft_p99_ms || 0,
      },
    ]);
  }, [data]);

  const channelOptions = useMemo(() => {
    return (data?.channels || []).map((channel) => ({
      value: channel.id,
      label: channelLabel(channel),
    }));
  }, [data]);

  const selectedChannels = useMemo(() => {
    const selected = new Set(selectedChannelIds);
    return (data?.channels || []).filter((channel) => selected.has(channel.id));
  }, [data, selectedChannelIds]);

  const channelMetricValues = useMemo(() => {
    return selectedChannels.flatMap((channel) =>
      (channel.series || []).map((point) => ({
        time: formatTime(point.time),
        channel: channelLabel(channel),
        value: point[selectedMetricOption.field] || 0,
      })),
    );
  }, [selectedChannels, selectedMetricOption]);

  const trafficSpec = useMemo(
    () => ({
      type: 'line',
      data: [{ id: 'traffic', values: trafficValues }],
      xField: 'time',
      yField: 'value',
      seriesField: 'metric',
      legends: { visible: true, orient: 'bottom' },
      title: { visible: true, text: '?? RPM / ???? TPM' },
      tooltip: { dimension: { visible: true } },
    }),
    [trafficValues],
  );

  const healthSpec = useMemo(
    () => ({
      type: 'line',
      data: [{ id: 'health', values: healthValues }],
      xField: 'time',
      yField: 'value',
      seriesField: 'metric',
      legends: { visible: true, orient: 'bottom' },
      title: { visible: true, text: '??? / ?? / ? Token' },
      tooltip: { dimension: { visible: true } },
    }),
    [healthValues],
  );

  const channelMetricSpec = useMemo(
    () => ({
      type: 'line',
      data: [{ id: 'channel-metric', values: channelMetricValues }],
      xField: 'time',
      yField: 'value',
      seriesField: 'channel',
      legends: { visible: true, orient: 'bottom', maxRow: 2 },
      title: {
        visible: true,
        text: `?? ${selectedMetricOption.label}`,
      },
      tooltip: {
        dimension: { visible: true },
        mark: { visible: true },
      },
    }),
    [channelMetricValues, selectedMetricOption],
  );

  const channelColumns = [
    {
      title: '??',
      dataIndex: 'name',
      width: 220,
      fixed: 'left',
      render: (_, record) => (
        <div>
          <Text strong>#{record.id}</Text>{' '}
          <Text>{record.name || record.monitor_key}</Text>
          <Text type='tertiary' size='small' style={{ display: 'block' }}>
            {record.monitor_key} / type {record.type}
          </Text>
        </div>
      ),
    },
    {
      title: '????',
      dataIndex: 'status',
      width: 110,
      render: (status, record) => statusTag(status, record.status_text),
    },
    {
      title: '??',
      dataIndex: 'requests',
      width: 100,
      sorter: (a, b) => a.requests - b.requests,
      render: (v) => formatNumber(v),
    },
    {
      title: '???? Token',
      dataIndex: 'provider_tokens',
      width: 120,
      sorter: (a, b) => a.provider_tokens - b.provider_tokens,
      render: (v) => formatNumber(v),
    },
    {
      title: '?? Token',
      dataIndex: 'tokens',
      width: 130,
      sorter: (a, b) => a.tokens - b.tokens,
      render: (v) => formatNumber(v),
    },
    {
      title: 'Cache ?/?',
      width: 130,
      render: (_, record) => (
        <Text type='tertiary'>
          {formatNumber(record.cached_tokens)} /{' '}
          {formatNumber(record.cache_creation_tokens)}
        </Text>
      ),
    },
    {
      title: '???',
      dataIndex: 'success_rate',
      width: 110,
      sorter: (a, b) => a.success_rate - b.success_rate,
      render: (v, record) => {
        const hasTraffic = record.requests > 0;
        const color = !hasTraffic
          ? 'grey'
          : v >= 99
            ? 'green'
            : v >= 95
              ? 'orange'
              : 'red';
        return (
          <Tag color={color}>
            {hasTraffic ? `${formatNumber(v, 2)}%` : '???'}
          </Tag>
        );
      },
    },
    {
      title: '??',
      dataIndex: 'errors',
      width: 90,
      sorter: (a, b) => a.errors - b.errors,
      render: (v) => (
        <Text type={v > 0 ? 'danger' : 'tertiary'}>{formatNumber(v)}</Text>
      ),
    },
    {
      title: '????',
      dataIndex: 'avg_latency_ms',
      width: 110,
      sorter: (a, b) => a.avg_latency_ms - b.avg_latency_ms,
      render: (v) => (v ? `${formatNumber(v, 0)} ms` : '-'),
    },
    {
      title: '?? P99',
      dataIndex: 'latency_p99_ms',
      width: 110,
      sorter: (a, b) => a.latency_p99_ms - b.latency_p99_ms,
      render: (v) => (v ? `${formatNumber(v, 0)} ms` : '-'),
    },
    {
      title: '? Token',
      dataIndex: 'avg_ttft_ms',
      width: 110,
      sorter: (a, b) => a.avg_ttft_ms - b.avg_ttft_ms,
      render: (v) => (v ? `${formatNumber(v, 0)} ms` : '-'),
    },
    {
      title: '? Token P99',
      dataIndex: 'ttft_p99_ms',
      width: 130,
      sorter: (a, b) => a.ttft_p99_ms - b.ttft_p99_ms,
      render: (v) => (v ? `${formatNumber(v, 0)} ms` : '-'),
    },
    {
      title: '????',
      dataIndex: 'upstream_latency_ms',
      width: 110,
      sorter: (a, b) => a.upstream_latency_ms - b.upstream_latency_ms,
      render: (v) => (v ? `${formatNumber(v, 0)} ms` : '-'),
    },
    {
      title: '?? P99',
      dataIndex: 'upstream_p99_ms',
      width: 110,
      sorter: (a, b) => a.upstream_p99_ms - b.upstream_p99_ms,
      render: (v) => (v ? `${formatNumber(v, 0)} ms` : '-'),
    },
    {
      title: '????/??',
      width: 130,
      render: (_, record) => (
        <Text
          type={
            record.upstream_errors + record.timeouts > 0 ? 'danger' : 'tertiary'
          }
        >
          {formatNumber(record.upstream_errors)} /{' '}
          {formatNumber(record.timeouts)}
        </Text>
      ),
    },
    {
      title: 'Fallback',
      dataIndex: 'fallbacks',
      width: 100,
      sorter: (a, b) => a.fallbacks - b.fallbacks,
      render: (v) => formatNumber(v),
    },
    {
      title: '????',
      dataIndex: 'last_test_time',
      width: 180,
      render: (v, record) =>
        v ? `${formatTime(v)} (${record.response_time || 0} ms)` : '-',
    },
  ];

  const logRows = useMemo(() => {
    return (logData?.rows || []).map((row, index) => ({
      ...row,
      _idx: index,
    }));
  }, [logData]);

  const logColumns = useMemo(() => {
    const fields =
      logData?.fields?.length > 0
        ? logData.fields
        : ['@timestamp', '@logStream', '@message'];
    return fields.map((field) => ({
      title: field,
      dataIndex: field,
      width: field === '@message' ? 520 : field === '@logStream' ? 260 : 180,
      render: (value) => (
        <Text
          size='small'
          style={{
            whiteSpace: field === '@message' ? 'pre-wrap' : 'normal',
            wordBreak: 'break-word',
          }}
        >
          {value || '-'}
        </Text>
      ),
    }));
  }, [logData]);

  const summary = data?.summary || {};

  return (
    <div className='mt-[60px] px-2'>
      <Card
        bodyStyle={{ padding: 16 }}
        title={
          <div className='flex items-center gap-2'>
            <ServerCog size={18} />
            <Title heading={5} style={{ margin: 0 }}>
              AWS ????
            </Title>
          </div>
        }
      >
        <div className='flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3'>
          <Space wrap>
            <Select
              style={{ width: 140 }}
              value={hours}
              onChange={setHours}
              optionList={hoursOptions}
            />
            <Select
              style={{ width: 130 }}
              value={period}
              onChange={setPeriod}
              optionList={periodOptions}
            />
            <Select
              style={{ width: 140 }}
              value={channelLimit}
              onChange={setChannelLimit}
              optionList={channelLimitOptions}
            />
            <Button
              theme='solid'
              type='primary'
              icon={<RefreshCw size={16} />}
              loading={loading}
              onClick={loadData}
            >
              ??
            </Button>
          </Space>
          <Text type='tertiary'>
            ??? CloudWatch / {data?.region || '-'} / {data?.namespace || '-'}{' '}
            / ?? {data?.period || '-'}s
          </Text>
        </div>
      </Card>

      <Tabs type='line' style={{ marginTop: 12 }}>
        <Tabs.TabPane tab='Metrics' itemKey='metrics'>
          {data ? (
            <Banner
              type='info'
              description={`?????${formatTime(data.start_time)} - ${formatTime(data.end_time)}?????????? CloudWatch ?????? Channel ???????????? ${data.channel_limit} ????`}
              style={{ marginTop: 12 }}
            />
          ) : null}

          <div className='grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-3 mt-3'>
            <StatCard
              icon={<Activity size={18} />}
              title='???'
              value={formatNumber(summary.requests)}
              sub={`?? ${formatNumber(summary.errors)}`}
            />
            <StatCard
              icon={<TrendingUp size={18} />}
              title='???'
              value={`${formatNumber(summary.success_rate, 2)}%`}
              sub='CloudWatch ErrorCount ??'
            />
            <StatCard
              icon={<Timer size={18} />}
              title='?? / ?? RPM'
              value={`${formatNumber(summary.avg_rpm, 2)} / ${formatNumber(summary.peak_rpm, 2)}`}
              sub='???????'
            />
            <StatCard
              icon={<TrendingUp size={18} />}
              title='?? / ?? TPM'
              value={`${formatNumber(summary.avg_provider_tpm, 2)} / ${formatNumber(summary.peak_provider_tpm, 2)}`}
              sub={`${formatNumber(summary.provider_tokens)} tokens?????`}
            />
            <StatCard
              icon={<Timer size={18} />}
              title='?? / P99 ??'
              value={
                summary.avg_latency_ms
                  ? `${formatNumber(summary.avg_latency_ms, 0)} / ${formatNumber(summary.latency_p99_ms, 0)} ms`
                  : '-'
              }
              sub='RequestLatencyMs'
            />
            <StatCard
              icon={<Timer size={18} />}
              title='? Token ?? / P99'
              value={
                summary.avg_ttft_ms
                  ? `${formatNumber(summary.avg_ttft_ms, 0)} / ${formatNumber(summary.ttft_p99_ms, 0)} ms`
                  : '-'
              }
              sub='TTFTMs??????'
            />
          </div>

          <div className='grid grid-cols-1 xl:grid-cols-2 gap-3 mt-3'>
            <Card bodyStyle={{ height: 360, padding: 8 }}>
              <VChart spec={trafficSpec} option={CHART_CONFIG} />
            </Card>
            <Card bodyStyle={{ height: 360, padding: 8 }}>
              <VChart spec={healthSpec} option={CHART_CONFIG} />
            </Card>
          </div>

          <Card
            title={
              <div className='flex items-center gap-2'>
                <Title heading={5} style={{ margin: 0 }}>
                  ??????
                </Title>
                <Tag>{selectedChannels.length}</Tag>
              </div>
            }
            style={{ marginTop: 12 }}
            bodyStyle={{ padding: 16 }}
          >
            <div className='grid grid-cols-1 lg:grid-cols-[1fr_180px] gap-3 mb-3'>
              <Select
                multiple
                filter
                style={{ width: '100%' }}
                placeholder='???????????????? 5 ?'
                value={selectedChannelIds}
                onChange={(ids) =>
                  setSelectedChannelIds(
                    (ids || []).slice(0, MAX_SELECTED_CHANNELS),
                  )
                }
                optionList={channelOptions}
                maxTagCount={3}
              />
              <Select
                style={{ width: '100%' }}
                value={channelMetric}
                onChange={setChannelMetric}
                optionList={channelMetricOptions.map(({ value, label }) => ({
                  value,
                  label,
                }))}
              />
            </div>
            <Text type='tertiary' size='small'>
              ?????{selectedMetricOption.label}
              {selectedMetricOption.suffix
                ? ` (${selectedMetricOption.suffix.trim()})`
                : ''}
              ??????? {MAX_SELECTED_CHANNELS} ???????????
            </Text>
            <div style={{ height: 380, marginTop: 8 }}>
              <VChart spec={channelMetricSpec} option={CHART_CONFIG} />
            </div>
          </Card>

          <Card
            title={
              <div className='flex items-center gap-2'>
                <Title heading={5} style={{ margin: 0 }}>
                  ??????
                </Title>
                <Tag>{data?.channels?.length || 0}</Tag>
              </div>
            }
            style={{ marginTop: 12 }}
            bodyStyle={{ padding: 0 }}
          >
            <Table
              columns={channelColumns}
              dataSource={data?.channels || []}
              rowKey='id'
              loading={loading}
              size='small'
              pagination={{ pageSize: 20 }}
              scroll={{ x: 1900 }}
            />
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane tab='Logs Insights' itemKey='logs'>
          <Card bodyStyle={{ padding: 16 }}>
            <div className='grid grid-cols-1 lg:grid-cols-[140px_120px_1fr_auto] gap-3 mb-3'>
              <Select
                style={{ width: '100%' }}
                value={logHours}
                onChange={setLogHours}
                optionList={hoursOptions}
              />
              <Select
                style={{ width: '100%' }}
                value={logLimit}
                onChange={setLogLimit}
                optionList={logLimitOptions}
              />
              <TextArea
                value={logQuery}
                onChange={setLogQuery}
                autosize={{ minRows: 3, maxRows: 8 }}
                placeholder='CloudWatch Logs Insights query'
              />
              <Button
                theme='solid'
                type='primary'
                icon={<RefreshCw size={16} />}
                loading={logLoading}
                onClick={loadLogs}
              >
                ????
              </Button>
            </div>
            <Banner
              type='info'
              description='?? CloudWatch Logs Insights ?? CLOUDWATCH_LOG_GROUP????? query???? request id?channel?error?latency ??????'
            />
          </Card>

          {logData ? (
            <Card
              style={{ marginTop: 12 }}
              bodyStyle={{ padding: 0 }}
              title={
                <div className='flex flex-col lg:flex-row lg:items-center lg:justify-between gap-2'>
                  <div className='flex items-center gap-2'>
                    <Title heading={5} style={{ margin: 0 }}>
                      CloudWatch ????
                    </Title>
                    <Tag>{logRows.length}</Tag>
                    {logData.partial ? <Tag color='orange'>Partial</Tag> : null}
                  </div>
                  <Text type='tertiary' size='small'>
                    {logData.region} / {logData.log_group} / {logData.status}
                  </Text>
                </div>
              }
            >
              <div className='px-4 py-3'>
                <Space wrap>
                  <Text type='tertiary' size='small'>
                    ???{formatTime(logData.start_time)} -{' '}
                    {formatTime(logData.end_time)}
                  </Text>
                  <Text type='tertiary' size='small'>
                    matched {formatNumber(logData.stats?.records_matched)}
                  </Text>
                  <Text type='tertiary' size='small'>
                    scanned {formatNumber(logData.stats?.records_scanned)}
                  </Text>
                  <Text type='tertiary' size='small'>
                    bytes {formatNumber(logData.stats?.bytes_scanned)}
                  </Text>
                </Space>
              </div>
              <Table
                columns={logColumns}
                dataSource={logRows}
                rowKey='_idx'
                loading={logLoading}
                size='small'
                pagination={{ pageSize: 20 }}
                scroll={{ x: Math.max(960, logColumns.length * 180) }}
              />
            </Card>
          ) : null}
        </Tabs.TabPane>
      </Tabs>
    </div>
  );
}
