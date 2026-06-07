import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Banner,
  Button,
  Card,
  Empty,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from '@douyinfe/semi-ui';
import {
  IllustrationNoResult,
  IllustrationNoResultDark,
} from '@douyinfe/semi-illustrations';
import { API, showError } from '../../helpers';

const { Text, Title } = Typography;

const CASE_OPTIONS = [
  { value: 'openai_chat', label: 'OpenAI Chat' },
  { value: 'openai_chat_stream', label: 'OpenAI Chat Stream' },
  { value: 'openai_responses', label: 'OpenAI Responses' },
  { value: 'openai_chat_image', label: 'OpenAI Chat + 图片输入' },
  { value: 'openai_stream_image', label: 'OpenAI Chat Stream + 图片输入' },
  { value: 'openai_responses_image', label: 'OpenAI Responses + 图片输入' },
  { value: 'openai_image', label: 'OpenAI Images' },
  { value: 'gemini_native', label: 'Gemini Native' },
  { value: 'gemini_stream', label: 'Gemini Stream' },
  { value: 'gemini_edit', label: 'Gemini Edit' },
];

const BillingProbePage = () => {
  const [channels, setChannels] = useState([]);
  const [tokens, setTokens] = useState([]);
  const [loadingMeta, setLoadingMeta] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [imagePreview, setImagePreview] = useState('');
  const fileInputRef = useRef(null);
  const [form, setForm] = useState({
    token_id: undefined,
    channel_id: undefined,
    models: [],
    cases: ['openai_chat'],
    prompt: 'Please reply with one short sentence for a billing validation probe.',
    input_image_data: '',
    input_image_mime_type: '',
    max_tokens: 32,
    timeout_seconds: 180,
    log_wait_seconds: 35,
  });

  const loadMeta = useCallback(async () => {
    setLoadingMeta(true);
    try {
      const [channelRes, tokenRes] = await Promise.all([
        API.get('/api/billing_probe/channels'),
        API.get('/api/billing_probe/tokens'),
      ]);
      if (channelRes.data.success) {
        setChannels(channelRes.data.data || []);
      } else {
        showError(channelRes.data.message);
      }
      if (tokenRes.data.success) {
        setTokens(tokenRes.data.data || []);
      } else {
        showError(tokenRes.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setLoadingMeta(false);
    }
  }, []);

  useEffect(() => {
    loadMeta();
  }, [loadMeta]);

  const selectedChannel = useMemo(
    () => channels.find((c) => String(c.id) === String(form.channel_id)),
    [channels, form.channel_id],
  );

  const modelOptions = useMemo(() => {
    const sourceChannels = selectedChannel ? [selectedChannel] : channels;
    const models = new Set();
    sourceChannels.forEach((channel) => {
      const rawModels = Array.isArray(channel.models)
        ? channel.models
        : String(channel.models || '').split(',');
      rawModels
        .map((m) => String(m).trim())
        .filter(Boolean)
        .forEach((m) => models.add(m));
    });
    return Array.from(models)
      .map((m) => m.trim())
      .filter(Boolean)
      .sort()
      .map((m) => ({ value: m, label: m }));
  }, [channels, selectedChannel]);

  const channelOptions = useMemo(
    () =>
      channels.map((c) => ({
        value: c.id,
        label: `#${c.id} ${c.name || ''} (${c.type})`,
      })),
    [channels],
  );

  const tokenOptions = useMemo(
    () =>
      tokens.map((t) => ({
        value: t.id,
        label: `#${t.id} ${t.name || ''} / ${t.username || `user ${t.user_id}`} / ${t.unlimited_quota ? 'unlimited' : t.remain_quota}`,
      })),
    [tokens],
  );

  const handleImageFile = (file) => {
    if (!file) return;
    if (!file.type?.startsWith('image/')) {
      showError('请选择图片文件');
      return;
    }
    if (file.size > 6 * 1024 * 1024) {
      showError('图片最大 6MB');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || '');
      setImagePreview(dataUrl);
      setForm((prev) => ({
        ...prev,
        input_image_data: dataUrl,
        input_image_mime_type: file.type || 'image/png',
      }));
    };
    reader.onerror = () => showError('读取图片失败');
    reader.readAsDataURL(file);
  };

  const clearInputImage = () => {
    setImagePreview('');
    setForm((prev) => ({
      ...prev,
      input_image_data: '',
      input_image_mime_type: '',
    }));
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const runProbe = async () => {
    if (!form.token_id) {
      showError('请选择测试 token');
      return;
    }
    if (!form.models || form.models.length === 0) {
      showError('请输入或选择模型');
      return;
    }
    if (!form.cases || form.cases.length === 0) {
      showError('请选择校验场景');
      return;
    }

    setRunning(true);
    setResult(null);
    try {
      const res = await API.post('/api/billing_probe/run', form);
      if (res.data.success) {
        setResult(res.data.data);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const columns = [
    {
      title: '模型 / 场景',
      dataIndex: 'name',
      width: 260,
      render: (_, record) => (
        <div>
          <Text strong>{record.model}</Text>
          <Text type='tertiary' style={{ display: 'block' }}>
            {record.case}
          </Text>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 140,
      render: (status, record) => (
        <div>
          <Tag color={status === 'pass' ? 'green' : status === 'warn' ? 'orange' : 'red'} size='small'>
            {status === 'pass' ? '通过' : status === 'warn' ? '警告' : '失败'}
          </Tag>
          {record.message && (
            <Text
              type={status === 'pass' ? 'tertiary' : 'danger'}
              size='small'
              style={{ display: 'block', marginTop: 4, wordBreak: 'break-word' }}
            >
              {record.message}
            </Text>
          )}
        </div>
      ),
    },
    { title: 'HTTP', dataIndex: 'http_status', width: 80 },
    { title: '日志', dataIndex: 'log_id', width: 90, render: (v) => (v ? `#${v}` : '-') },
    { title: '渠道', dataIndex: 'channel_id', width: 90, render: (v) => (v ? `#${v}` : '-') },
    {
      title: 'Token',
      width: 160,
      render: (_, record) => (
        <div>
          <Text>prompt: {record.prompt_tokens ?? '-'}</Text>
          <Text type='tertiary' style={{ display: 'block' }}>
            completion: {record.completion_tokens ?? '-'}
          </Text>
          {record.image_tokens ? (
            <Text type='tertiary' style={{ display: 'block' }}>
              image: {record.image_tokens}
            </Text>
          ) : null}
          {record.input_image_tokens ? (
            <Text type='tertiary' style={{ display: 'block' }}>
              input image: {record.input_image_tokens}
            </Text>
          ) : null}
        </div>
      ),
    },
    {
      title: 'Quota 复算',
      width: 170,
      render: (_, record) => (
        <div>
          <Text>{record.quota ?? '-'}</Text>
          <Text type='tertiary' style={{ display: 'block' }}>
            expected: {record.expected_quota ?? '-'}
          </Text>
          <Text type={record.delta === 0 ? 'success' : 'danger'} style={{ display: 'block' }}>
            delta: {record.delta ?? '-'}
          </Text>
        </div>
      ),
    },
    {
      title: '实际扣费',
      dataIndex: 'billing',
      width: 210,
      render: (billing) => {
        if (!billing) return '-';
        return (
          <div>
            <Text type={billing.settled ? 'success' : 'danger'}>
              user: {billing.actual_user_quota_debit ?? '-'}
            </Text>
            <Text type='tertiary' style={{ display: 'block' }}>
              token: {billing.actual_token_debit ?? '-'}
            </Text>
            <Text type='tertiary' style={{ display: 'block' }}>
              expected: {billing.expected_debit ?? '-'}
            </Text>
            {billing.channel_id ? (
              <Text type='tertiary' style={{ display: 'block' }}>
                channel: {billing.actual_channel_used_delta ?? '-'}
              </Text>
            ) : null}
          </div>
        );
      },
    },
  ];

  return (
    <div className='mt-[60px] px-2'>
      <Card
        title={
          <Title heading={5} style={{ margin: 0 }}>
            计费校验
          </Title>
        }
        style={{ marginBottom: 16 }}
      >
        <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4'>
          <div>
            <Form.Label>测试 Token</Form.Label>
            <Select
              filter
              style={{ width: '100%' }}
              placeholder='选择实际扣费 token'
              value={form.token_id}
              onChange={(v) => setForm((prev) => ({ ...prev, token_id: v }))}
              optionList={tokenOptions}
              loading={loadingMeta}
            />
          </div>
          <div>
            <Form.Label>指定渠道</Form.Label>
            <Select
              filter
              style={{ width: '100%' }}
              placeholder='可选；强制走某个渠道'
              value={form.channel_id}
              onChange={(v) => setForm((prev) => ({ ...prev, channel_id: v }))}
              optionList={channelOptions}
              loading={loadingMeta}
              showClear
            />
          </div>
          <div className='lg:col-span-2'>
            <Form.Label>模型</Form.Label>
            <Select
              multiple
              filter
              allowCreate
              style={{ width: '100%' }}
              placeholder='输入或选择模型'
              value={form.models}
              onChange={(v) => setForm((prev) => ({ ...prev, models: v }))}
              optionList={modelOptions}
              maxTagCount={3}
            />
          </div>
        </div>

        <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4'>
          <div className='lg:col-span-2'>
            <Form.Label>校验场景</Form.Label>
            <Select
              multiple
              style={{ width: '100%' }}
              value={form.cases}
              onChange={(v) => setForm((prev) => ({ ...prev, cases: v }))}
              optionList={CASE_OPTIONS}
            />
          </div>
          <div>
            <Form.Label>Max Tokens</Form.Label>
            <InputNumber
              style={{ width: '100%' }}
              min={1}
              max={1000000}
              value={form.max_tokens}
              onChange={(v) => setForm((prev) => ({ ...prev, max_tokens: v }))}
            />
          </div>
          <div>
            <Form.Label>等待日志/扣费秒数</Form.Label>
            <InputNumber
              style={{ width: '100%' }}
              min={5}
              max={120}
              value={form.log_wait_seconds}
              onChange={(v) => setForm((prev) => ({ ...prev, log_wait_seconds: v }))}
            />
          </div>
        </div>

        <div className='mb-4'>
          <Form.Label>Prompt</Form.Label>
          <Input
            value={form.prompt}
            onChange={(v) => setForm((prev) => ({ ...prev, prompt: v }))}
          />
        </div>

        <div className='mb-4'>
          <Form.Label>图片输入</Form.Label>
          <div className='flex items-center gap-3 flex-wrap'>
            <input
              ref={fileInputRef}
              type='file'
              accept='image/*'
              style={{ display: 'none' }}
              onChange={(e) => handleImageFile(e.target.files?.[0])}
            />
            <Button onClick={() => fileInputRef.current?.click()}>
              选择图片
            </Button>
            {imagePreview ? (
              <>
                <img
                  src={imagePreview}
                  alt='input preview'
                  style={{ width: 48, height: 48, objectFit: 'cover', borderRadius: 4 }}
                />
                <Text type='tertiary'>{form.input_image_mime_type}</Text>
                <Button type='danger' onClick={clearInputImage}>
                  移除图片
                </Button>
              </>
            ) : (
              <Text type='tertiary'>用于 Gemini Edit 和 OpenAI 图片输入场景</Text>
            )}
          </div>
        </div>

        <Space>
          <Button theme='solid' type='primary' loading={running} onClick={runProbe}>
            {running ? '校验中...' : '开始校验'}
          </Button>
          <Button onClick={loadMeta} loading={loadingMeta}>
            刷新列表
          </Button>
        </Space>
      </Card>

      {result && (
        <Card
          title={
            <div className='flex items-center gap-3'>
              <Title heading={5} style={{ margin: 0 }}>
                校验结果
              </Title>
              <Tag color='blue'>{result.base_url}</Tag>
              <Text type='tertiary'>
                {(result.results || []).filter((r) => r.status === 'pass').length}/{(result.results || []).length} 通过
              </Text>
            </div>
          }
        >
          {(result.results || []).some((r) => r.status !== 'pass') && (
            <Banner
              type='warning'
              description='存在未通过项，请查看状态、Quota 复算和实际扣费列。'
              style={{ marginBottom: 12 }}
            />
          )}
          <Table
            columns={columns}
            dataSource={result.results || []}
            rowKey='name'
            pagination={false}
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
    </div>
  );
};

export default BillingProbePage;
