import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Table,
  Button,
  Form,
  Modal,
  Space,
  Popconfirm,
  Typography,
  Tag,
  Empty,
  Descriptions,
} from '@douyinfe/semi-ui';
import {
  IllustrationNoResult,
  IllustrationNoResultDark,
} from '@douyinfe/semi-illustrations';
import { Plus, Download, Trash2 } from 'lucide-react';
import dayjs from 'dayjs';
import CardPro from '../../components/common/ui/CardPro';
import { API, showError, showSuccess, renderQuota, timestamp2string } from '../../helpers';
import { createCardProPagination } from '../../helpers/utils';
import { useIsMobile } from '../../hooks/common/useIsMobile';
import { ITEMS_PER_PAGE } from '../../constants';
import { DATE_RANGE_PRESETS } from '../../constants/console.constants';

const { Text } = Typography;

const InvoicePage = () => {
  const { t } = useTranslation();
  const isMobile = useIsMobile();

  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activePage, setActivePage] = useState(1);
  const [pageSize, setPageSize] = useState(ITEMS_PER_PAGE);
  const [total, setTotal] = useState(0);
  const [username, setUsername] = useState('');
  const [dateRange, setDateRange] = useState([]);

  const [generateModalVisible, setGenerateModalVisible] = useState(false);
  const [generating, setGenerating] = useState(false);

  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [detailInvoice, setDetailInvoice] = useState(null);
  const [detailItems, setDetailItems] = useState([]);

  const loadInvoices = useCallback(async () => {
    setLoading(true);
    try {
      let url = `/api/invoice/?p=${activePage}&page_size=${pageSize}`;
      if (username) {
        url += `&username=${encodeURIComponent(username)}`;
      }
      if (dateRange && dateRange.length === 2) {
        url += `&start_timestamp=${Math.floor(new Date(dateRange[0]).getTime() / 1000)}`;
        url += `&end_timestamp=${Math.floor(new Date(dateRange[1]).getTime() / 1000)}`;
      }
      const res = await API.get(url);
      const { success, message, data } = res.data;
      if (success) {
        setInvoices(data.items || []);
        setTotal(data.total || 0);
      } else {
        showError(message);
      }
    } catch (err) {
      showError(err.message);
    } finally {
      setLoading(false);
    }
  }, [activePage, pageSize, username, dateRange]);

  useEffect(() => {
    loadInvoices();
  }, [loadInvoices]);

  const handlePageChange = (page) => setActivePage(page);
  const handlePageSizeChange = (size) => {
    setPageSize(size);
    setActivePage(1);
  };

  const handleSearch = (values) => {
    setUsername(values.username || '');
    setDateRange(values.dateRange || []);
    setActivePage(1);
  };

  const handleGenerate = async (values) => {
    if (!values.user_id) {
      showError(t('请输入用户 ID'));
      return;
    }
    if (!values.dateRange || values.dateRange.length !== 2) {
      showError(t('请选择时间范围'));
      return;
    }

    setGenerating(true);
    try {
      const res = await API.post('/api/invoice/generate', {
        user_id: parseInt(values.user_id),
        start_timestamp: Math.floor(new Date(values.dateRange[0]).getTime() / 1000),
        end_timestamp: Math.floor(new Date(values.dateRange[1]).getTime() / 1000),
        note: values.note || '',
      });
      const { success, message } = res.data;
      if (success) {
        showSuccess(t('账单生成成功'));
        setGenerateModalVisible(false);
        loadInvoices();
      } else {
        showError(message);
      }
    } catch (err) {
      showError(err.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      const res = await API.delete(`/api/invoice/${id}`);
      const { success, message } = res.data;
      if (success) {
        showSuccess(t('删除成功'));
        loadInvoices();
      } else {
        showError(message);
      }
    } catch (err) {
      showError(err.message);
    }
  };

  const handleExport = async (id) => {
    try {
      const res = await API.get(`/api/invoice/${id}/export`, {
        responseType: 'blob',
      });
      const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const disposition = res.headers['content-disposition'];
      const filename = disposition
        ? disposition.split('filename=')[1]?.replace(/"/g, '')
        : `invoice-${id}.csv`;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      showError(err.message || t('导出失败'));
    }
  };

  const handleViewDetail = (invoice) => {
    setDetailInvoice(invoice);
    try {
      const items = invoice.items ? JSON.parse(invoice.items) : [];
      setDetailItems(items);
    } catch {
      setDetailItems([]);
    }
    setDetailModalVisible(true);
  };

  const columns = [
    {
      title: t('账单编号'),
      dataIndex: 'invoice_no',
      width: 180,
      render: (text, record) => (
        <Text
          link
          onClick={() => handleViewDetail(record)}
          style={{ cursor: 'pointer' }}
        >
          {text}
        </Text>
      ),
    },
    {
      title: t('用户'),
      dataIndex: 'username',
      width: 120,
    },
    {
      title: t('账单周期'),
      dataIndex: 'start_timestamp',
      width: 260,
      render: (_, record) => (
        <span>
          {timestamp2string(record.start_timestamp)} ~ {timestamp2string(record.end_timestamp)}
        </span>
      ),
    },
    {
      title: t('总消耗'),
      dataIndex: 'total_quota',
      width: 120,
      render: (text) => renderQuota(text),
    },
    {
      title: t('总金额 (USD)'),
      dataIndex: 'total_amount',
      width: 130,
      render: (text) => `$${Number(text).toFixed(4)}`,
    },
    {
      title: t('创建时间'),
      dataIndex: 'created_at',
      width: 180,
      render: (text) => timestamp2string(text),
    },
    {
      title: t('操作'),
      dataIndex: 'action',
      width: 160,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          <Button
            theme='borderless'
            type='tertiary'
            size='small'
            icon={<Download size={14} />}
            onClick={() => handleExport(record.id)}
          >
            CSV
          </Button>
          <Popconfirm
            title={t('确认删除')}
            content={t('确定要删除这条账单吗？')}
            onConfirm={() => handleDelete(record.id)}
          >
            <Button
              theme='borderless'
              type='danger'
              size='small'
              icon={<Trash2 size={14} />}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const detailColumns = [
    {
      title: t('模型'),
      dataIndex: 'model_name',
    },
    {
      title: t('请求次数'),
      dataIndex: 'request_count',
    },
    {
      title: t('输入 Tokens'),
      dataIndex: 'prompt_tokens',
      render: (text) => text?.toLocaleString(),
    },
    {
      title: t('输出 Tokens'),
      dataIndex: 'completion_tokens',
      render: (text) => text?.toLocaleString(),
    },
    {
      title: t('消耗'),
      dataIndex: 'quota',
      render: (text) => renderQuota(text),
    },
    {
      title: t('金额 (USD)'),
      dataIndex: 'amount',
      render: (text) => `$${Number(text).toFixed(6)}`,
    },
  ];

  const filterArea = (
    <Form
      layout='horizontal'
      onSubmit={handleSearch}
      labelPosition='inset'
      style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}
    >
      <Form.Input
        field='username'
        label={t('用户名')}
        placeholder={t('输入用户名')}
        style={{ width: 160 }}
        noLabel
      />
      <Form.DatePicker
        field='dateRange'
        type='dateTimeRange'
        label={t('时间范围')}
        style={{ width: 340 }}
        presets={DATE_RANGE_PRESETS.map((preset) => ({
          text: t(preset.text),
          start: preset.start(),
          end: preset.end(),
        }))}
        noLabel
      />
      <Button htmlType='submit' theme='solid' type='primary'>
        {t('搜索')}
      </Button>
    </Form>
  );

  const statsArea = (
    <Space>
      <Tag size='large' color='blue'>
        {t('共')} {total} {t('条账单')}
      </Tag>
      <Button
        theme='solid'
        type='primary'
        icon={<Plus size={14} />}
        onClick={() => setGenerateModalVisible(true)}
      >
        {t('生成账单')}
      </Button>
    </Space>
  );

  return (
    <div className='mt-[60px] px-2'>
      <CardPro
        type='type2'
        statsArea={statsArea}
        searchArea={filterArea}
        paginationArea={createCardProPagination({
          currentPage: activePage,
          pageSize: pageSize,
          total: total,
          onPageChange: handlePageChange,
          onPageSizeChange: handlePageSizeChange,
          isMobile: isMobile,
          t: t,
        })}
        t={t}
      >
        <Table
          columns={columns}
          dataSource={invoices}
          loading={loading}
          pagination={false}
          rowKey='id'
          scroll={{ x: 'max-content' }}
          empty={
            <Empty
              image={<IllustrationNoResult />}
              darkModeImage={<IllustrationNoResultDark />}
              description={t('暂无数据')}
            />
          }
        />
      </CardPro>

      {/* Generate Invoice Modal */}
      <Modal
        title={t('生成账单')}
        visible={generateModalVisible}
        onCancel={() => setGenerateModalVisible(false)}
        footer={null}
        width={520}
      >
        <Form onSubmit={handleGenerate} labelPosition='left' labelWidth={100}>
          <Form.Input
            field='user_id'
            label={t('用户 ID')}
            placeholder={t('输入用户 ID')}
            rules={[{ required: true, message: t('请输入用户 ID') }]}
          />
          <Form.DatePicker
            field='dateRange'
            type='dateTimeRange'
            label={t('时间范围')}
            style={{ width: '100%' }}
            rules={[{ required: true, message: t('请选择时间范围') }]}
            presets={DATE_RANGE_PRESETS.map((preset) => ({
              text: t(preset.text),
              start: preset.start(),
              end: preset.end(),
            }))}
          />
          <Form.TextArea
            field='note'
            label={t('备注')}
            placeholder={t('可选备注信息')}
            rows={3}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
            <Button onClick={() => setGenerateModalVisible(false)}>
              {t('取消')}
            </Button>
            <Button htmlType='submit' theme='solid' type='primary' loading={generating}>
              {t('生成')}
            </Button>
          </div>
        </Form>
      </Modal>

      {/* Invoice Detail Modal */}
      <Modal
        title={detailInvoice ? `${t('账单详情')} - ${detailInvoice.invoice_no}` : t('账单详情')}
        visible={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={
          detailInvoice ? (
            <Button
              icon={<Download size={14} />}
              onClick={() => handleExport(detailInvoice.id)}
            >
              {t('导出 CSV')}
            </Button>
          ) : null
        }
        width={800}
      >
        {detailInvoice && (
          <>
            <Descriptions
              data={[
                { key: t('账单编号'), value: detailInvoice.invoice_no },
                { key: t('用户'), value: detailInvoice.username },
                {
                  key: t('账单周期'),
                  value: `${timestamp2string(detailInvoice.start_timestamp)} ~ ${timestamp2string(detailInvoice.end_timestamp)}`,
                },
                { key: t('总消耗'), value: renderQuota(detailInvoice.total_quota) },
                { key: t('总金额'), value: `$${Number(detailInvoice.total_amount).toFixed(4)}` },
                { key: t('备注'), value: detailInvoice.note || '-' },
                { key: t('创建时间'), value: timestamp2string(detailInvoice.created_at) },
              ]}
              style={{ marginBottom: 16 }}
            />
            <Table
              columns={detailColumns}
              dataSource={detailItems}
              pagination={false}
              rowKey='model_name'
              size='small'
              empty={
                <Empty
                  image={<IllustrationNoResult />}
                  darkModeImage={<IllustrationNoResultDark />}
                  description={t('暂无明细')}
                />
              }
            />
          </>
        )}
      </Modal>
    </div>
  );
};

export default InvoicePage;
