import React, { useState, useCallback } from 'react';
import {
  Card,
  Table,
  Tag,
  Button,
  Select,
  DatePicker,
  Input,
  Typography,
  Space,
  Modal,
  Popconfirm,
  Checkbox,
  Banner,
} from '@douyinfe/semi-ui';
import {
  IconDownload,
  IconSearch,
  IconRefresh,
} from '@douyinfe/semi-icons';
import { useTranslation } from 'react-i18next';
import { API, showError, showSuccess } from '../../helpers';
import { renderQuota } from '../../helpers/render';

const { Title, Text } = Typography;

const Claude200KFixPage = () => {
  const { t } = useTranslation();

  const [loading, setLoading] = useState(false);
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [dateRange, setDateRange] = useState([]);
  const [username, setUsername] = useState('');
  const [modelName, setModelName] = useState('');
  const [channel, setChannel] = useState('');

  const [summary, setSummary] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(false);

  const [selectedIds, setSelectedIds] = useState([]);
  const [applying, setApplying] = useState(false);
  const [ignoring, setIgnoring] = useState(false);

  const [applyModalVisible, setApplyModalVisible] = useState(false);
  const [applyPreview, setApplyPreview] = useState([]);

  const buildQueryParams = useCallback(() => {
    const params = new URLSearchParams();
    if (dateRange && dateRange.length === 2) {
      params.set(
        'start_timestamp',
        Math.floor(new Date(dateRange[0]).getTime() / 1000),
      );
      params.set(
        'end_timestamp',
        Math.floor(new Date(dateRange[1]).getTime() / 1000),
      );
    }
    if (username) params.set('username', username);
    if (modelName) params.set('model_name', modelName);
    if (channel) params.set('channel', channel);
    return params;
  }, [dateRange, username, modelName, channel]);

  const loadRecords = useCallback(
    async (p = page, ps = pageSize) => {
      setLoading(true);
      try {
        const params = buildQueryParams();
        params.set('p', p);
        params.set('page_size', ps);
        const res = await API.get(
          `/api/claude_200k_fix/scan?${params.toString()}`,
        );
        if (res.data.success) {
          setRecords(res.data.data.records || []);
          setTotal(res.data.data.total || 0);
          setPage(p);
          setPageSize(ps);
          setSelectedIds([]);
        } else {
          showError(res.data.message);
        }
      } catch (e) {
        showError(e.message);
      } finally {
        setLoading(false);
      }
    },
    [buildQueryParams, page, pageSize],
  );

  const loadSummary = useCallback(async () => {
    setLoadingSummary(true);
    try {
      const params = buildQueryParams();
      const res = await API.get(
        `/api/claude_200k_fix/summary?${params.toString()}`,
      );
      if (res.data.success) {
        setSummary(res.data.data);
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setLoadingSummary(false);
    }
  }, [buildQueryParams]);

  const handleSearch = () => {
    loadRecords(1, pageSize);
    loadSummary();
  };

  const handleExport = () => {
    const params = buildQueryParams();
    window.open(`/api/claude_200k_fix/export?${params.toString()}`, '_blank');
  };

  const handleApplyClick = () => {
    const selected = records.filter(
      (r) =>
        selectedIds.includes(r.log.id) && r.can_recalc && r.quota_diff > 0,
    );
    if (selected.length === 0) {
      showError('没有可补扣的记录');
      return;
    }
    setApplyPreview(selected);
    setApplyModalVisible(true);
  };

  const handleApplyConfirm = async () => {
    setApplying(true);
    try {
      const ids = applyPreview.map((r) => r.log.id);
      const res = await API.post('/api/claude_200k_fix/apply', {
        log_ids: ids,
      });
      if (res.data.success) {
        showSuccess(
          `补扣完成：${res.data.data.applied_count} 条记录，总差额 ${renderQuota(res.data.data.total_diff)}`,
        );
        setApplyModalVisible(false);
        loadRecords(page, pageSize);
        loadSummary();
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setApplying(false);
    }
  };

  const handleIgnore = async () => {
    if (selectedIds.length === 0) {
      showError('请先选择记录');
      return;
    }
    setIgnoring(true);
    try {
      const res = await API.post('/api/claude_200k_fix/ignore', {
        log_ids: selectedIds,
      });
      if (res.data.success) {
        showSuccess(`已忽略 ${res.data.data.ignored_count} 条记录`);
        loadRecords(page, pageSize);
        loadSummary();
      } else {
        showError(res.data.message);
      }
    } catch (e) {
      showError(e.message);
    } finally {
      setIgnoring(false);
    }
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return '-';
    return new Date(timestamp * 1000).toLocaleString();
  };

  const columns = [
    {
      title: '',
      dataIndex: 'select',
      width: 50,
      render: (_, record) => (
        <Checkbox
          checked={selectedIds.includes(record.log.id)}
          onChange={(e) => {
            if (e.target.checked) {
              setSelectedIds((prev) => [...prev, record.log.id]);
            } else {
              setSelectedIds((prev) =>
                prev.filter((id) => id !== record.log.id),
              );
            }
          }}
        />
      ),
    },
    {
      title: 'ID',
      dataIndex: 'log.id',
      width: 80,
      render: (_, record) => record.log.id,
    },
    {
      title: '用户',
      dataIndex: 'log.username',
      width: 100,
      render: (_, record) => record.log.username,
    },
    {
      title: '模型',
      dataIndex: 'log.model_name',
      width: 180,
      render: (_, record) => (
        <Text ellipsis={{ showTooltip: true }} style={{ maxWidth: 180 }}>
          {record.log.model_name}
        </Text>
      ),
    },
    {
      title: '提示 Tokens',
      dataIndex: 'log.prompt_tokens',
      width: 110,
      render: (_, record) => record.log.prompt_tokens?.toLocaleString(),
    },
    {
      title: '补全 Tokens',
      dataIndex: 'log.completion_tokens',
      width: 110,
      render: (_, record) => record.log.completion_tokens?.toLocaleString(),
    },
    {
      title: '总输入',
      dataIndex: 'total_input',
      width: 110,
      render: (_, record) => {
        const val = record.total_input;
        return (
          <Text type={val > 200000 ? 'danger' : undefined}>
            {val?.toLocaleString()}
          </Text>
        );
      },
    },
    {
      title: '原始扣费',
      dataIndex: 'log.quota',
      width: 110,
      render: (_, record) => renderQuota(record.log.quota),
    },
    {
      title: '应收扣费',
      dataIndex: 'correct_quota',
      width: 110,
      render: (_, record) =>
        record.can_recalc ? renderQuota(record.correct_quota) : '-',
    },
    {
      title: '差额',
      dataIndex: 'quota_diff',
      width: 110,
      render: (_, record) => {
        if (!record.can_recalc) return '-';
        const diff = record.quota_diff;
        if (diff > 0) {
          return (
            <Tag color="red" size="small">
              +{renderQuota(diff)}
            </Tag>
          );
        } else if (diff < 0) {
          return (
            <Tag color="green" size="small">
              {renderQuota(diff)}
            </Tag>
          );
        }
        return (
          <Tag color="grey" size="small">
            0
          </Tag>
        );
      },
    },
    {
      title: '价格段',
      dataIndex: 'tier_range',
      width: 100,
      render: (_, record) =>
        record.can_recalc ? record.tier_range : record.skip_reason || '-',
    },
    {
      title: 'API 类型',
      dataIndex: 'is_native_api',
      width: 90,
      render: (_, record) =>
        record.can_recalc ? (
          record.is_native_api ? (
            <Tag size="small">原生</Tag>
          ) : (
            <Tag size="small">兼容</Tag>
          )
        ) : (
          '-'
        ),
    },
    {
      title: '时间',
      dataIndex: 'log.created_at',
      width: 160,
      render: (_, record) => formatTime(record.log.created_at),
    },
  ];

  const selectAll = () => {
    const allIds = records.map((r) => r.log.id);
    setSelectedIds(allIds);
  };

  const selectNone = () => {
    setSelectedIds([]);
  };

  const selectAffected = () => {
    const ids = records
      .filter((r) => r.can_recalc && r.quota_diff > 0)
      .map((r) => r.log.id);
    setSelectedIds(ids);
  };

  return (
    <div className="mt-[60px] px-2">
      <Card style={{ marginBottom: 16 }}>
        <Title heading={4}>Claude 200K 计费修复工具</Title>
        <Banner
          type="info"
          description="扫描历史 Claude 消费记录，使用当前最新的分段定价重算应收额度，发现计费偏差。仅 Root 管理员可操作。"
          style={{ marginBottom: 16 }}
        />

        <Space wrap style={{ marginBottom: 16 }}>
          <DatePicker
            type="dateRange"
            placeholder={['开始日期', '结束日期']}
            value={dateRange}
            onChange={setDateRange}
            style={{ width: 260 }}
          />
          <Input
            placeholder="用户名"
            value={username}
            onChange={setUsername}
            style={{ width: 140 }}
          />
          <Input
            placeholder="模型名（支持 LIKE）"
            value={modelName}
            onChange={setModelName}
            style={{ width: 200 }}
          />
          <Input
            placeholder="渠道 ID"
            value={channel}
            onChange={setChannel}
            style={{ width: 100 }}
          />
          <Button
            icon={<IconSearch />}
            theme="solid"
            onClick={handleSearch}
            loading={loading}
          >
            扫描
          </Button>
          <Button icon={<IconDownload />} onClick={handleExport}>
            导出 CSV
          </Button>
        </Space>
      </Card>

      {summary && (
        <Card style={{ marginBottom: 16 }}>
          <Title heading={5}>汇总统计</Title>
          <Space wrap style={{ gap: 24 }}>
            <div>
              <Text type="tertiary">扫描记录数</Text>
              <br />
              <Text strong style={{ fontSize: 20 }}>
                {summary.total_records}
              </Text>
            </div>
            <div>
              <Text type="tertiary">需补扣记录</Text>
              <br />
              <Text strong style={{ fontSize: 20, color: 'var(--semi-color-danger)' }}>
                {summary.affected_records}
              </Text>
            </div>
            <div>
              <Text type="tertiary">总差额</Text>
              <br />
              <Text strong style={{ fontSize: 20, color: 'var(--semi-color-danger)' }}>
                {renderQuota(summary.total_diff)}
              </Text>
            </div>
          </Space>

          {summary.user_diffs && summary.user_diffs.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Text strong>按用户分组</Text>
              <Table
                size="small"
                dataSource={summary.user_diffs}
                pagination={false}
                columns={[
                  {
                    title: '用户',
                    dataIndex: 'username',
                    width: 120,
                  },
                  {
                    title: '记录数',
                    dataIndex: 'count',
                    width: 80,
                  },
                  {
                    title: '差额',
                    dataIndex: 'diff',
                    width: 120,
                    render: (val) => (
                      <Tag color="red" size="small">
                        +{renderQuota(val)}
                      </Tag>
                    ),
                  },
                ]}
                style={{ marginTop: 8 }}
              />
            </div>
          )}

          {summary.model_diffs && summary.model_diffs.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Text strong>按模型分组</Text>
              <Table
                size="small"
                dataSource={summary.model_diffs}
                pagination={false}
                columns={[
                  {
                    title: '模型',
                    dataIndex: 'model_name',
                    width: 200,
                  },
                  {
                    title: '记录数',
                    dataIndex: 'count',
                    width: 80,
                  },
                  {
                    title: '差额',
                    dataIndex: 'diff',
                    width: 120,
                    render: (val) => (
                      <Tag color="red" size="small">
                        +{renderQuota(val)}
                      </Tag>
                    ),
                  },
                ]}
                style={{ marginTop: 8 }}
              />
            </div>
          )}
        </Card>
      )}

      <Card>
        <Space style={{ marginBottom: 12 }}>
          <Button size="small" onClick={selectAll}>
            全选
          </Button>
          <Button size="small" onClick={selectNone}>
            取消全选
          </Button>
          <Button size="small" onClick={selectAffected}>
            选择需补扣
          </Button>
          <Text type="tertiary">
            已选 {selectedIds.length} 条
          </Text>
          <Button
            theme="solid"
            type="danger"
            size="small"
            onClick={handleApplyClick}
            loading={applying}
            disabled={selectedIds.length === 0}
          >
            批量补扣
          </Button>
          <Popconfirm
            title="确认忽略选中的记录？忽略后不会再出现在扫描结果中。"
            onConfirm={handleIgnore}
          >
            <Button
              size="small"
              loading={ignoring}
              disabled={selectedIds.length === 0}
            >
              批量忽略
            </Button>
          </Popconfirm>
        </Space>

        <Table
          columns={columns}
          dataSource={records}
          loading={loading}
          rowKey={(record) => record.log?.id}
          pagination={{
            currentPage: page,
            pageSize: pageSize,
            total: total,
            onPageChange: (p) => loadRecords(p, pageSize),
            onPageSizeChange: (ps) => loadRecords(1, ps),
            showSizeChanger: true,
            pageSizeOpts: [10, 20, 50, 100],
          }}
          scroll={{ x: 1500 }}
          size="small"
        />
      </Card>

      <Modal
        title="确认补扣"
        visible={applyModalVisible}
        onOk={handleApplyConfirm}
        onCancel={() => setApplyModalVisible(false)}
        okText="确认补扣"
        cancelText="取消"
        confirmLoading={applying}
        width={600}
      >
        <Banner
          type="warning"
          description="补扣操作将扣减用户余额，此操作不可撤销。请仔细确认。"
          style={{ marginBottom: 16 }}
        />
        <Text>
          将对 <Text strong>{applyPreview.length}</Text> 条记录执行补扣，总差额：
          <Text strong type="danger">
            {renderQuota(
              applyPreview.reduce((sum, r) => sum + r.quota_diff, 0),
            )}
          </Text>
        </Text>
        <Table
          size="small"
          dataSource={applyPreview.slice(0, 50)}
          pagination={false}
          columns={[
            {
              title: 'ID',
              dataIndex: 'log.id',
              width: 60,
              render: (_, r) => r.log.id,
            },
            {
              title: '用户',
              dataIndex: 'log.username',
              width: 100,
              render: (_, r) => r.log.username,
            },
            {
              title: '模型',
              dataIndex: 'log.model_name',
              width: 160,
              render: (_, r) => (
                <Text ellipsis={{ showTooltip: true }} style={{ maxWidth: 160 }}>
                  {r.log.model_name}
                </Text>
              ),
            },
            {
              title: '差额',
              dataIndex: 'quota_diff',
              width: 100,
              render: (_, r) => (
                <Tag color="red" size="small">
                  +{renderQuota(r.quota_diff)}
                </Tag>
              ),
            },
          ]}
          style={{ marginTop: 12 }}
          scroll={{ y: 300 }}
        />
        {applyPreview.length > 50 && (
          <Text type="tertiary" style={{ marginTop: 8 }}>
            仅显示前 50 条，共 {applyPreview.length} 条
          </Text>
        )}
      </Modal>
    </div>
  );
};

export default Claude200KFixPage;
