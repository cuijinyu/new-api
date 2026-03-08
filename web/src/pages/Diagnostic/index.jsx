import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card,
  Form,
  Select,
  Button,
  Table,
  Tag,
  RadioGroup,
  Radio,
  InputNumber,
  Switch,
  Collapsible,
  Typography,
  Space,
  Spin,
  Banner,
  Descriptions,
  Empty,
} from '@douyinfe/semi-ui';
import {
  IllustrationNoResult,
  IllustrationNoResultDark,
} from '@douyinfe/semi-illustrations';
import { useTranslation } from 'react-i18next';
import { API, showError } from '../../helpers';

const { Text, Title } = Typography;

const TEST_TYPES = [
  { value: 'standard', label: '标准测试' },
  { value: 'cache', label: '缓存检测' },
  { value: 'thinking', label: 'Thinking 模式' },
  { value: 'long_context', label: '长上下文' },
  { value: 'pricing_verify', label: '计费验证' },
];

const ENDPOINT_TYPES = [
  { value: '', label: '自动检测' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'gemini', label: 'Gemini' },
];

const DiagnosticPage = () => {
  const { t } = useTranslation();
  const [channels, setChannels] = useState([]);
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [selectedChannelIds, setSelectedChannelIds] = useState([]);
  const [model, setModel] = useState('');
  const [testType, setTestType] = useState('standard');
  const [testing, setTesting] = useState(false);
  const [results, setResults] = useState(null);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [expandedRows, setExpandedRows] = useState([]);
  const historyRef = useRef([]);

  const [options, setOptions] = useState({
    enable_cache: false,
    cache_ttl: '5m',
    enable_thinking: false,
    thinking_type: 'enabled',
    thinking_budget: 10000,
    thinking_effort: 'high',
    target_input_tokens: 210000,
    max_tokens: 50,
    endpoint_type: '',
    stream: false,
  });

  const availableModels = React.useMemo(() => {
    if (selectedChannelIds.length === 0 || channels.length === 0) return [];
    const union = new Set();
    selectedChannelIds.forEach((id) => {
      // eslint-disable-next-line eqeqeq
      const ch = channels.find((c) => c.id == id);
      if (ch && ch.models) {
        ch.models.split(',').map((m) => m.trim()).filter(Boolean).forEach((m) => union.add(m));
      }
    });
    return Array.from(union).sort();
  }, [selectedChannelIds, channels]);

  const loadChannels = useCallback(async () => {
    setLoadingChannels(true);
    try {
      const res = await API.get('/api/diagnostic/channels');
      if (res.data.success) {
        setChannels(res.data.data);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    }
    setLoadingChannels(false);
  }, []);

  useEffect(() => {
    loadChannels();
  }, [loadChannels]);

  const handleTest = async () => {
    if (selectedChannelIds.length === 0) {
      showError('请选择至少一个渠道');
      return;
    }
    if (!model) {
      showError('请输入模型名称');
      return;
    }

    setTesting(true);
    setResults(null);
    setExpandedRows([]);

    try {
      const payload = {
        channel_ids: selectedChannelIds,
        model,
        test_type: testType,
        options: { ...options },
      };

      if (testType === 'cache') {
        payload.options.enable_cache = true;
      }
      if (testType === 'thinking') {
        payload.options.enable_thinking = true;
        if (payload.options.max_tokens < payload.options.thinking_budget + 1000) {
          payload.options.max_tokens = payload.options.thinking_budget + 1000;
        }
      }
      if (testType === 'long_context') {
        if (!payload.options.target_input_tokens || payload.options.target_input_tokens < 1000) {
          payload.options.target_input_tokens = 210000;
        }
      }

      const res = await API.post('/api/diagnostic/test', payload);
      if (res.data.success) {
        const data = res.data.data;
        setResults(data);
        const errorRows = (data.results || [])
          .filter((r) => r.status !== 'success')
          .map((r) => r.channel_id);
        setExpandedRows(errorRows);
        const entry = {
          id: Date.now(),
          time: new Date().toLocaleTimeString(),
          testType: data.test_type,
          model: data.model,
          channelCount: data.results.length,
          successCount: data.results.filter((r) => r.status === 'success').length,
        };
        historyRef.current = [entry, ...historyRef.current].slice(0, 20);
        setHistory(historyRef.current);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    }
    setTesting(false);
  };

  const channelOptions = channels.map((ch) => ({
    value: ch.id,
    label: `#${ch.id} ${ch.name}${ch.status !== 1 ? ' [禁用]' : ''}`,
  }));

  const resultColumns = [
    {
      title: '渠道',
      dataIndex: 'channel_name',
      width: 160,
      render: (text, record) => (
        <div>
          <Text strong>#{record.channel_id}</Text>{' '}
          <Text>{text}</Text>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (status, record) => (
        <div>
          <Tag color={status === 'success' ? 'green' : 'red'} size='small'>
            {status === 'success' ? '成功' : '失败'}
          </Tag>
          {record.error && (
            <Text type='danger' size='small' style={{ display: 'block', marginTop: 4, fontSize: 12, lineHeight: '16px', wordBreak: 'break-all' }}>
              {record.error.length > 120 ? record.error.substring(0, 120) + '...' : record.error}
            </Text>
          )}
        </div>
      ),
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 90,
      render: (ms) => `${ms}ms`,
      sorter: (a, b) => a.duration_ms - b.duration_ms,
    },
    {
      title: 'Prompt',
      dataIndex: 'usage',
      width: 90,
      render: (u) => u?.prompt_tokens ?? '-',
    },
    {
      title: 'Completion',
      dataIndex: 'usage',
      width: 100,
      render: (u) => u?.completion_tokens ?? '-',
      key: 'completion',
    },
    {
      title: 'Cached',
      dataIndex: 'usage',
      width: 80,
      render: (u) => {
        const val = u?.cached_tokens;
        return val > 0 ? <Text type='success'>{val}</Text> : (val === 0 ? '0' : '-');
      },
      key: 'cached',
    },
    {
      title: 'Cache Write',
      dataIndex: 'usage',
      width: 100,
      render: (u) => {
        if (!u) return '-';
        const parts = [];
        if (u.cache_creation_5m_tokens > 0) parts.push(`5m:${u.cache_creation_5m_tokens}`);
        if (u.cache_creation_1h_tokens > 0) parts.push(`1h:${u.cache_creation_1h_tokens}`);
        if (parts.length === 0 && u.cache_creation_tokens > 0) return u.cache_creation_tokens;
        return parts.length > 0 ? parts.join(' / ') : (u.cache_creation_tokens || '-');
      },
      key: 'cache_write',
    },
    {
      title: 'Reasoning',
      dataIndex: 'usage',
      width: 90,
      render: (u) => {
        const val = u?.reasoning_tokens;
        return val > 0 ? <Text type='warning'>{val}</Text> : (val === 0 ? '0' : '-');
      },
      key: 'reasoning',
    },
    {
      title: '费用',
      dataIndex: 'pricing',
      width: 120,
      render: (p) => {
        if (!p) return '-';
        return p.total_cost_usd > 0
          ? `$${p.total_cost_usd.toFixed(6)}`
          : p.use_tiered_pricing ? '$0' : '倍率计费';
      },
    },
    {
      title: '检测项',
      dataIndex: 'checks',
      render: (checks) => {
        if (!checks || checks.length === 0) return '-';
        const passed = checks.filter((c) => c.passed).length;
        const failed = checks.filter((c) => !c.passed).length;
        return (
          <Space>
            {passed > 0 && <Tag color='green' size='small'>{passed} 通过</Tag>}
            {failed > 0 && <Tag color='red' size='small'>{failed} 失败</Tag>}
          </Space>
        );
      },
    },
  ];

  const expandRowRender = (record) => {
    if (record.error) {
      return (
        <Banner type='danger' description={record.error} style={{ margin: '8px 0' }} />
      );
    }

    return (
      <div className='p-4 space-y-4'>
        {record.pricing && record.pricing.use_tiered_pricing && (
          <Descriptions
            data={[
              { key: '价格区间', value: record.pricing.tier_used },
              { key: '输入价 ($/MTok)', value: `$${record.pricing.input_price_per_mtok}` },
              { key: '输出价 ($/MTok)', value: `$${record.pricing.output_price_per_mtok}` },
              { key: '缓存命中价 ($/MTok)', value: `$${record.pricing.cache_hit_price_per_mtok}` },
              { key: '5m 缓存写入价 ($/MTok)', value: `$${record.pricing.cache_store_5m_price_per_mtok}` },
              { key: '1h 缓存写入价 ($/MTok)', value: `$${record.pricing.cache_store_1h_price_per_mtok}` },
              { key: '总费用', value: `$${record.pricing.total_cost_usd?.toFixed(6)}` },
            ]}
            row
            size='small'
          />
        )}

        {record.checks && record.checks.length > 0 && (
          <div>
            <Text strong style={{ marginBottom: 8, display: 'block' }}>检测项详情</Text>
            <Table
              columns={[
                { title: '检测项', dataIndex: 'name', width: 180 },
                {
                  title: '结果',
                  dataIndex: 'passed',
                  width: 80,
                  render: (v) => (
                    <Tag color={v ? 'green' : 'red'} size='small'>
                      {v ? '通过' : '失败'}
                    </Tag>
                  ),
                },
                { title: '详情', dataIndex: 'detail' },
              ]}
              dataSource={record.checks}
              pagination={false}
              size='small'
              rowKey='name'
            />
          </div>
        )}
      </div>
    );
  };

  const highlightDifferences = (data) => {
    if (!data || data.length <= 1) return data;
    const successResults = data.filter((r) => r.status === 'success' && r.usage);
    if (successResults.length <= 1) return data;

    const fields = ['prompt_tokens', 'completion_tokens', 'cached_tokens', 'cache_creation_tokens'];
    const hasDiff = {};
    fields.forEach((field) => {
      const values = new Set(successResults.map((r) => r.usage[field]));
      if (values.size > 1) hasDiff[field] = true;
    });

    return data.map((r) => ({ ...r, _hasDiff: hasDiff }));
  };

  return (
    <div className='mt-[60px] px-2'>
      <Card
        title={
          <Title heading={5} style={{ margin: 0 }}>
            模型诊断工具
          </Title>
        }
        style={{ marginBottom: 16 }}
      >
        <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4'>
          <div className='lg:col-span-2'>
            <Form.Label>渠道选择</Form.Label>
            <Select
              multiple
              filter
              style={{ width: '100%' }}
              placeholder='选择渠道（可多选）'
              value={selectedChannelIds}
              onChange={setSelectedChannelIds}
              loading={loadingChannels}
              maxTagCount={3}
              optionList={channelOptions}
            />
          </div>

          <div>
            <Form.Label>模型</Form.Label>
            <Select
              filter
              allowCreate
              key={selectedChannelIds.join(',')}
              style={{ width: '100%' }}
              placeholder='输入或选择模型'
              value={model}
              onChange={setModel}
              optionList={availableModels.map((m) => ({ value: m, label: m }))}
            />
          </div>

          <div>
            <Form.Label>测试类型</Form.Label>
            <Select
              style={{ width: '100%' }}
              value={testType}
              onChange={setTestType}
              optionList={TEST_TYPES}
            />
          </div>
        </div>

        <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4'>
          <div>
            <Form.Label>端点类型</Form.Label>
            <Select
              style={{ width: '100%' }}
              value={options.endpoint_type}
              onChange={(v) => setOptions((o) => ({ ...o, endpoint_type: v }))}
              optionList={ENDPOINT_TYPES}
            />
          </div>

          <div>
            <Form.Label>Max Tokens</Form.Label>
            <InputNumber
              style={{ width: '100%' }}
              value={options.max_tokens}
              onChange={(v) => setOptions((o) => ({ ...o, max_tokens: v }))}
              min={1}
              max={1000000}
            />
          </div>

          <div className='flex items-end'>
            <Switch
              checked={options.stream}
              onChange={(v) => setOptions((o) => ({ ...o, stream: v }))}
            />
            <Text style={{ marginLeft: 8 }}>流式请求</Text>
          </div>
        </div>

        {testType === 'cache' && (
          <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4'>
            <div>
              <Form.Label>缓存 TTL</Form.Label>
              <RadioGroup
                value={options.cache_ttl}
                onChange={(e) => setOptions((o) => ({ ...o, cache_ttl: e.target.value }))}
              >
                <Radio value='5m'>5 分钟</Radio>
                <Radio value='1h'>1 小时</Radio>
              </RadioGroup>
            </div>
          </div>
        )}

        {testType === 'thinking' && (
          <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4'>
            <div>
              <Form.Label>Thinking Type</Form.Label>
              <RadioGroup
                value={options.thinking_type}
                onChange={(e) => setOptions((o) => ({ ...o, thinking_type: e.target.value }))}
              >
                <Radio value='enabled'>enabled</Radio>
                <Radio value='adaptive'>adaptive</Radio>
              </RadioGroup>
            </div>
            {options.thinking_type === 'enabled' && (
              <div>
                <Form.Label>Budget Tokens</Form.Label>
                <InputNumber
                  style={{ width: '100%' }}
                  value={options.thinking_budget}
                  onChange={(v) => setOptions((o) => ({ ...o, thinking_budget: v }))}
                  min={1000}
                  max={100000}
                  step={1000}
                />
              </div>
            )}
            {options.thinking_type === 'adaptive' && (
              <div>
                <Form.Label>Effort</Form.Label>
                <Select
                  style={{ width: '100%' }}
                  value={options.thinking_effort}
                  onChange={(v) => setOptions((o) => ({ ...o, thinking_effort: v }))}
                  optionList={[
                    { value: 'low', label: 'low' },
                    { value: 'medium', label: 'medium' },
                    { value: 'high', label: 'high' },
                    { value: 'max', label: 'max' },
                  ]}
                />
              </div>
            )}
          </div>
        )}

        {testType === 'long_context' && (
          <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4'>
            <div>
              <Form.Label>目标输入 Tokens</Form.Label>
              <InputNumber
                style={{ width: '100%' }}
                value={options.target_input_tokens}
                onChange={(v) => setOptions((o) => ({ ...o, target_input_tokens: v }))}
                min={1000}
                max={1000000}
                step={10000}
              />
            </div>
          </div>
        )}

        <div className='flex items-center gap-4'>
          <Button
            theme='solid'
            type='primary'
            loading={testing}
            onClick={handleTest}
            disabled={selectedChannelIds.length === 0 || !model}
          >
            {testing ? '检测中...' : '开始检测'}
          </Button>
          <Text type='tertiary'>
            已选 {selectedChannelIds.length} 个渠道
          </Text>
        </div>
      </Card>

      {results && (
        <Card
          title={
            <div className='flex items-center gap-3'>
              <Title heading={5} style={{ margin: 0 }}>
                检测结果
              </Title>
              <Tag>{results.test_type}</Tag>
              <Tag color='blue'>{results.model}</Tag>
              <Text type='tertiary'>
                {results.results.filter((r) => r.status === 'success').length}/{results.results.length} 成功
              </Text>
            </div>
          }
          style={{ marginBottom: 16 }}
        >
          <Table
            columns={resultColumns}
            dataSource={highlightDifferences(results.results)}
            rowKey='channel_id'
            pagination={false}
            expandedRowRender={expandRowRender}
            expandedRowKeys={expandedRows}
            onExpandedRowsChange={(rows) => setExpandedRows(rows)}
            size='small'
            empty={
              <Empty
                image={<IllustrationNoResult />}
                darkModeImage={<IllustrationNoResultDark />}
                description='暂无结果'
              />
            }
          />
        </Card>
      )}

      {history.length > 0 && (
        <Card
          title={
            <div
              className='flex items-center gap-2 cursor-pointer'
              onClick={() => setShowHistory(!showHistory)}
            >
              <Title heading={5} style={{ margin: 0 }}>
                历史记录
              </Title>
              <Tag size='small'>{history.length}</Tag>
            </div>
          }
        >
          <Collapsible isOpen={showHistory}>
            <Table
              columns={[
                { title: '时间', dataIndex: 'time', width: 100 },
                { title: '类型', dataIndex: 'testType', width: 100, render: (v) => <Tag size='small'>{v}</Tag> },
                { title: '模型', dataIndex: 'model', width: 200 },
                { title: '渠道数', dataIndex: 'channelCount', width: 80 },
                {
                  title: '结果',
                  dataIndex: 'successCount',
                  width: 100,
                  render: (v, record) => (
                    <Text type={v === record.channelCount ? 'success' : 'warning'}>
                      {v}/{record.channelCount} 成功
                    </Text>
                  ),
                },
              ]}
              dataSource={history}
              rowKey='id'
              pagination={false}
              size='small'
            />
          </Collapsible>
        </Card>
      )}
    </div>
  );
};

export default DiagnosticPage;
