import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Table,
  Tag,
  Button,
  Select,
  DatePicker,
  Input,
  InputNumber,
  Upload,
  Typography,
  Space,
  Modal,
  Form,
  Popconfirm,
  Notification,
} from '@douyinfe/semi-ui';
import { IconUpload, IconDelete, IconPlus, IconDownload } from '@douyinfe/semi-icons';
import { useTranslation } from 'react-i18next';
import { API, showError, showSuccess } from '../../helpers';

const { Title, Text } = Typography;

const STATUS_MAP = {
  normal: { color: 'green', label: '正常' },
  abnormal: { color: 'red', label: '异常' },
  missing_upstream: { color: 'orange', label: '缺少上游' },
  missing_system: { color: 'orange', label: '缺少系统' },
  pending: { color: 'grey', label: '待处理' },
};

const ReconciliationPage = () => {
  const { t } = useTranslation();

  const [channels, setChannels] = useState([]);
  const [loadingChannels, setLoadingChannels] = useState(false);

  const [discounts, setDiscounts] = useState([]);
  const [loadingDiscounts, setLoadingDiscounts] = useState(false);
  const [discountModalVisible, setDiscountModalVisible] = useState(false);
  const [discountForm, setDiscountForm] = useState({ channel_id: '', model: '', discount_rate: 1.0, note: '' });

  const [uploadDateRange, setUploadDateRange] = useState([]);
  const [uploadChannelId, setUploadChannelId] = useState('');
  const [uploadSource, setUploadSource] = useState('');
  const [uploadFile, setUploadFile] = useState(null);
  const [uploading, setUploading] = useState(false);

  const [runDateRange, setRunDateRange] = useState([]);
  const [runChannelId, setRunChannelId] = useState('');
  const [running, setRunning] = useState(false);

  const [results, setResults] = useState([]);
  const [resultTotal, setResultTotal] = useState(0);
  const [resultPage, setResultPage] = useState(1);
  const [resultPageSize, setResultPageSize] = useState(20);
  const [filterDateRange, setFilterDateRange] = useState([]);
  const [filterChannelId, setFilterChannelId] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [loadingResults, setLoadingResults] = useState(false);

  const formatDate = (d) => {
    if (!d) return '';
    const date = new Date(d);
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  };

  const parseDateRange = (dates) => {
    if (!dates || dates.length !== 2) return ['', ''];
    return [formatDate(dates[0]), formatDate(dates[1])];
  };

  const loadChannels = useCallback(async () => {
    setLoadingChannels(true);
    try {
      const res = await API.get('/api/channel/?p=1&page_size=1000');
      if (res.data.success) {
        const list = res.data.data?.items || res.data.data?.data || res.data.data || [];
        setChannels(Array.isArray(list) ? list : []);
      }
    } catch (e) {
      showError(e.message);
    }
    setLoadingChannels(false);
  }, []);

  const loadDiscounts = useCallback(async () => {
    setLoadingDiscounts(true);
    try {
      const res = await API.get('/api/recon/discounts');
      if (res.data.success) {
        setDiscounts(res.data.data || []);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    }
    setLoadingDiscounts(false);
  }, []);

  const loadResults = useCallback(async () => {
    setLoadingResults(true);
    try {
      const params = new URLSearchParams();
      params.set('p', resultPage);
      params.set('page_size', resultPageSize);
      const [startDate, endDate] = parseDateRange(filterDateRange);
      if (startDate) params.set('start_date', startDate);
      if (endDate) params.set('end_date', endDate);
      if (filterChannelId) params.set('channel_id', filterChannelId);
      if (filterStatus) params.set('status', filterStatus);

      const res = await API.get(`/api/recon/results?${params.toString()}`);
      if (res.data.success) {
        const d = res.data.data;
        setResults(d.items || []);
        setResultTotal(d.total || 0);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    }
    setLoadingResults(false);
  }, [resultPage, resultPageSize, filterDateRange, filterChannelId, filterStatus]);

  useEffect(() => { loadChannels(); }, [loadChannels]);
  useEffect(() => { loadDiscounts(); }, [loadDiscounts]);
  useEffect(() => { loadResults(); }, [loadResults]);

  const channelOptions = channels.map((ch) => ({
    value: ch.id,
    label: `#${ch.id} ${ch.name}`,
  }));

  const getChannelName = (id) => {
    const ch = channels.find((c) => c.id === id);
    return ch ? `#${ch.id} ${ch.name}` : `#${id}`;
  };

  const handleSaveDiscount = async () => {
    if (!discountForm.channel_id || !discountForm.model) {
      showError('渠道和模型必填');
      return;
    }
    try {
      const res = await API.post('/api/recon/discounts', {
        channel_id: Number(discountForm.channel_id),
        model: discountForm.model,
        discount_rate: discountForm.discount_rate,
        note: discountForm.note,
      });
      if (res.data.success) {
        showSuccess('保存成功');
        setDiscountModalVisible(false);
        setDiscountForm({ channel_id: '', model: '', discount_rate: 1.0, note: '' });
        loadDiscounts();
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    }
  };

  const handleDeleteDiscount = async (id) => {
    try {
      const res = await API.delete(`/api/recon/discounts?id=${id}`);
      if (res.data.success) {
        showSuccess('删除成功');
        loadDiscounts();
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    }
  };

  const handleUpload = async () => {
    const [startDate, endDate] = parseDateRange(uploadDateRange);
    if (!startDate || !endDate || !uploadChannelId || !uploadSource) {
      showError('日期范围、渠道和来源必填');
      return;
    }
    if (!uploadFile) {
      showError('请选择文件');
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('start_date', startDate);
      formData.append('end_date', endDate);
      formData.append('channel_id', uploadChannelId);
      formData.append('source', uploadSource);
      formData.append('file', uploadFile);

      const res = await API.post('/api/recon/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      if (res.data.success) {
        showSuccess(`上传成功，共 ${res.data.data.count} 条记录`);
        setUploadFile(null);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    }
    setUploading(false);
  };

  const handleRun = async () => {
    const [startDate, endDate] = parseDateRange(runDateRange);
    if (!startDate || !endDate) {
      showError('请选择对账日期范围');
      return;
    }
    setRunning(true);
    try {
      const payload = { start_date: startDate, end_date: endDate };
      if (runChannelId) payload.channel_id = Number(runChannelId);

      const res = await API.post('/api/recon/run', payload);
      if (res.data.success) {
        const d = res.data.data;
        Notification.success({
          title: '对账完成',
          content: `共 ${d.total} 条：正常 ${d.normal}，异常 ${d.abnormal}，缺失 ${d.missing}`,
          duration: 5,
        });
        setFilterDateRange(runDateRange);
        setResultPage(1);
        loadResults();
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    }
    setRunning(false);
  };

  const discountColumns = [
    { title: '渠道', dataIndex: 'channel_id', width: 160, render: (v) => getChannelName(v) },
    { title: '模型', dataIndex: 'model', width: 200 },
    { title: '折扣比例', dataIndex: 'discount_rate', width: 100, render: (v) => `${(v * 100).toFixed(1)}%` },
    { title: '备注', dataIndex: 'note' },
    {
      title: '操作', width: 80,
      render: (_, record) => (
        <Popconfirm title='确认删除？' onConfirm={() => handleDeleteDiscount(record.id)}>
          <Button icon={<IconDelete />} type='danger' size='small' theme='borderless' />
        </Popconfirm>
      ),
    },
  ];

  const resultColumns = [
    { title: '日期', dataIndex: 'recon_date', width: 100 },
    {
      title: '渠道', dataIndex: 'channel_id', width: 140,
      render: (v, record) => record.channel_name || getChannelName(v),
    },
    { title: '来源', dataIndex: 'source', width: 80 },
    { title: '模型', dataIndex: 'model', width: 180 },
    { title: '系统请求', dataIndex: 'system_requests', width: 90, align: 'right' },
    { title: '上游请求', dataIndex: 'upstream_requests', width: 90, align: 'right' },
    {
      title: '系统Token', width: 110, align: 'right',
      render: (_, r) => ((r.system_prompt_tokens || 0) + (r.system_completion_tokens || 0)).toLocaleString(),
    },
    {
      title: '上游Token', width: 110, align: 'right',
      render: (_, r) => ((r.upstream_prompt_tokens || 0) + (r.upstream_completion_tokens || 0)).toLocaleString(),
    },
    {
      title: 'Token差异率', dataIndex: 'token_diff_rate', width: 100, align: 'right',
      render: (v) => {
        const pct = ((v || 0) * 100).toFixed(2);
        return <Text type={v > 0.02 ? 'danger' : 'success'}>{pct}%</Text>;
      },
    },
    {
      title: '系统额度', dataIndex: 'system_quota', width: 100, align: 'right',
      render: (v) => (v || 0).toLocaleString(),
    },
    {
      title: '折扣', dataIndex: 'discount_rate', width: 70, align: 'right',
      render: (v) => `${((v || 1) * 100).toFixed(0)}%`,
    },
    {
      title: '预期费用(分)', dataIndex: 'expected_amount_cent', width: 110, align: 'right',
      render: (v) => (v || 0).toLocaleString(),
    },
    {
      title: '上游费用(分)', dataIndex: 'upstream_amount_cent', width: 110, align: 'right',
      render: (v) => (v || 0).toLocaleString(),
    },
    {
      title: '费用差异(分)', dataIndex: 'amount_diff_cent', width: 110, align: 'right',
      render: (v) => {
        const val = v || 0;
        return <Text type={Math.abs(val) > 0 ? (val > 0 ? 'warning' : 'danger') : 'success'}>{val.toLocaleString()}</Text>;
      },
    },
    {
      title: '费用差异率', dataIndex: 'amount_diff_rate', width: 100, align: 'right',
      render: (v) => {
        const pct = ((v || 0) * 100).toFixed(2);
        return <Text type={v > 0.02 ? 'danger' : 'success'}>{pct}%</Text>;
      },
    },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (v) => {
        const s = STATUS_MAP[v] || STATUS_MAP.pending;
        return <Tag color={s.color} size='small'>{s.label}</Tag>;
      },
    },
    { title: '备注', dataIndex: 'remark', width: 120, ellipsis: true },
  ];

  const uploadDateValid = uploadDateRange && uploadDateRange.length === 2;

  return (
    <div className='mt-[60px] px-2'>
      {/* 折扣配置 */}
      <Card
        title={<Title heading={5} style={{ margin: 0 }}>折扣配置</Title>}
        headerExtraContent={
          <Button icon={<IconPlus />} theme='solid' size='small' onClick={() => setDiscountModalVisible(true)}>
            添加折扣
          </Button>
        }
        style={{ marginBottom: 16 }}
      >
        <Table
          columns={discountColumns}
          dataSource={discounts}
          rowKey='id'
          pagination={false}
          loading={loadingDiscounts}
          size='small'
          empty='暂无折扣配置'
        />
      </Card>

      {/* 上传上游账单 */}
      <Card
        title={<Title heading={5} style={{ margin: 0 }}>上传上游账单</Title>}
        headerExtraContent={
          <Button
            icon={<IconDownload />}
            size='small'
            onClick={() => {
              const link = document.createElement('a');
              link.href = '/api/recon/template';
              link.download = 'upstream_template.csv';
              link.click();
            }}
          >
            下载模板
          </Button>
        }
        style={{ marginBottom: 16 }}
      >
        <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-4'>
          <div>
            <Form.Label>账单日期范围</Form.Label>
            <DatePicker
              style={{ width: '100%' }}
              type='dateRange'
              onChange={(dates) => setUploadDateRange(dates || [])}
            />
          </div>
          <div>
            <Form.Label>渠道</Form.Label>
            <Select
              style={{ width: '100%' }}
              placeholder='选择渠道'
              filter
              optionList={channelOptions}
              loading={loadingChannels}
              onChange={(v) => setUploadChannelId(v)}
            />
          </div>
          <div>
            <Form.Label>来源</Form.Label>
            <Input
              placeholder='如 openai / anthropic'
              value={uploadSource}
              onChange={setUploadSource}
            />
          </div>
          <div>
            <Form.Label>文件 (CSV/JSON)</Form.Label>
            <Upload
              action=''
              accept='.csv,.json'
              limit={1}
              beforeUpload={({ file }) => { setUploadFile(file.fileInstance); return false; }}
              onRemove={() => setUploadFile(null)}
              draggable
              dragMainText='点击或拖拽上传'
              dragSubText='支持 CSV / JSON'
              style={{ width: '100%' }}
            />
          </div>
          <div className='flex items-end'>
            <Button
              icon={<IconUpload />}
              theme='solid'
              loading={uploading}
              onClick={handleUpload}
              disabled={!uploadDateValid || !uploadChannelId || !uploadSource || !uploadFile}
            >
              上传
            </Button>
          </div>
        </div>
        <Text type='tertiary' size='small'>
          提示：CSV 中可包含 recon_date 列指定每行的日期；若无该列，所有行默认使用范围起始日期。
        </Text>
      </Card>

      {/* 执行对账 */}
      <Card title={<Title heading={5} style={{ margin: 0 }}>执行对账</Title>} style={{ marginBottom: 16 }}>
        <Space>
          <DatePicker
            type='dateRange'
            onChange={(dates) => setRunDateRange(dates || [])}
          />
          <Select
            style={{ width: 200 }}
            placeholder='渠道（可选，不选则全部）'
            filter
            showClear
            optionList={channelOptions}
            loading={loadingChannels}
            onChange={(v) => setRunChannelId(v || '')}
          />
          <Button
            theme='solid'
            type='warning'
            loading={running}
            onClick={handleRun}
            disabled={!runDateRange || runDateRange.length !== 2}
          >
            执行对账
          </Button>
        </Space>
      </Card>

      {/* 对账结果 */}
      <Card title={<Title heading={5} style={{ margin: 0 }}>对账结果</Title>}>
        <div className='flex gap-4 mb-4 flex-wrap'>
          <DatePicker
            type='dateRange'
            onChange={(dates) => { setFilterDateRange(dates || []); setResultPage(1); }}
          />
          <Select
            style={{ width: 200 }}
            placeholder='筛选渠道'
            filter
            showClear
            optionList={channelOptions}
            loading={loadingChannels}
            onChange={(v) => { setFilterChannelId(v || ''); setResultPage(1); }}
          />
          <Select
            style={{ width: 150 }}
            placeholder='筛选状态'
            showClear
            optionList={Object.entries(STATUS_MAP).map(([k, v]) => ({ value: k, label: v.label }))}
            onChange={(v) => { setFilterStatus(v || ''); setResultPage(1); }}
          />
        </div>
        <Table
          columns={resultColumns}
          dataSource={results}
          rowKey='id'
          loading={loadingResults}
          size='small'
          scroll={{ x: 1800 }}
          pagination={{
            currentPage: resultPage,
            pageSize: resultPageSize,
            total: resultTotal,
            onPageChange: setResultPage,
            onPageSizeChange: (size) => { setResultPageSize(size); setResultPage(1); },
            showSizeChanger: true,
            pageSizeOpts: [10, 20, 50, 100],
          }}
          empty='暂无对账结果'
        />
      </Card>

      {/* 折扣配置弹窗 */}
      <Modal
        title='添加/编辑折扣'
        visible={discountModalVisible}
        onOk={handleSaveDiscount}
        onCancel={() => setDiscountModalVisible(false)}
        okText='保存'
        cancelText='取消'
      >
        <Form layout='vertical'>
          <Form.Slot label='渠道'>
            <Select
              style={{ width: '100%' }}
              placeholder='选择渠道'
              filter
              optionList={channelOptions}
              loading={loadingChannels}
              value={discountForm.channel_id}
              onChange={(v) => setDiscountForm((f) => ({ ...f, channel_id: v }))}
            />
          </Form.Slot>
          <Form.Slot label='模型'>
            <Input
              placeholder='如 gpt-4o'
              value={discountForm.model}
              onChange={(v) => setDiscountForm((f) => ({ ...f, model: v }))}
            />
          </Form.Slot>
          <Form.Slot label='折扣比例'>
            <InputNumber
              style={{ width: '100%' }}
              value={discountForm.discount_rate}
              onChange={(v) => setDiscountForm((f) => ({ ...f, discount_rate: v }))}
              min={0.01}
              max={10}
              step={0.01}
              precision={4}
              suffix='（1.0 = 无折扣，0.8 = 8折）'
            />
          </Form.Slot>
          <Form.Slot label='备注'>
            <Input
              placeholder='可选备注'
              value={discountForm.note}
              onChange={(v) => setDiscountForm((f) => ({ ...f, note: v }))}
            />
          </Form.Slot>
        </Form>
      </Modal>
    </div>
  );
};

export default ReconciliationPage;
