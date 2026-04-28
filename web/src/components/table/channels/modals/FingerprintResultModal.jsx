import React from 'react';
import { Modal, Table, Tag, Typography, Descriptions } from '@douyinfe/semi-ui';

const ProbeTag = ({ pass, t }) => (
  <Tag color={pass ? 'green' : 'red'} shape='circle' size='small'>
    {pass ? t('通过') : t('未通过')}
  </Tag>
);

const FingerprintResultModal = ({
  showFingerprintModal,
  setShowFingerprintModal,
  fingerprintResults,
  fingerprintLoading,
  t,
}) => {
  const results = fingerprintResults || [];

  const columns = [
    {
      title: t('渠道'),
      dataIndex: 'channel_name',
      width: 160,
      render: (text, record) => (
        <Typography.Text>
          #{record.channel_id} {text}
        </Typography.Text>
      ),
    },
    {
      title: t('模型'),
      dataIndex: 'model',
      width: 180,
    },
    {
      title: t('弯引号'),
      dataIndex: 'curly_quote_pass',
      width: 90,
      align: 'center',
      render: (pass) => <ProbeTag pass={pass} t={t} />,
    },
    {
      title: t('身份认知'),
      dataIndex: 'identity_pass',
      width: 90,
      align: 'center',
      render: (pass) => <ProbeTag pass={pass} t={t} />,
    },
    {
      title: t('提示词防护'),
      dataIndex: 'sys_prompt_pass',
      width: 100,
      align: 'center',
      render: (pass) => <ProbeTag pass={pass} t={t} />,
    },
    {
      title: t('得分'),
      dataIndex: 'score',
      width: 70,
      align: 'center',
      render: (score) => (
        <Typography.Text strong>{score}/3</Typography.Text>
      ),
    },
    {
      title: t('结果'),
      dataIndex: 'authentic',
      width: 90,
      align: 'center',
      render: (authentic, record) => {
        if (record.error) {
          return (
            <Tag color='orange' shape='circle' size='small'>
              {t('错误')}
            </Tag>
          );
        }
        return (
          <Tag
            color={authentic ? 'green' : 'red'}
            shape='circle'
            size='small'
          >
            {authentic ? t('正品') : t('异常')}
          </Tag>
        );
      },
    },
  ];

  const expandRowRender = (record) => {
    const items = [];
    if (record.identity_reply) {
      items.push({
        key: t('身份回复'),
        value: (
          <Typography.Paragraph
            ellipsis={{ rows: 3, expandable: true }}
            style={{ marginBottom: 0 }}
          >
            {record.identity_reply}
          </Typography.Paragraph>
        ),
      });
    }
    if (record.sys_prompt_reply) {
      items.push({
        key: t('提示词回复'),
        value: (
          <Typography.Paragraph
            ellipsis={{ rows: 3, expandable: true }}
            style={{ marginBottom: 0 }}
          >
            {record.sys_prompt_reply}
          </Typography.Paragraph>
        ),
      });
    }
    if (record.curly_quote_raw) {
      items.push({
        key: t('弯引号回复'),
        value: (
          <Typography.Paragraph
            ellipsis={{ rows: 2, expandable: true }}
            style={{ marginBottom: 0 }}
          >
            {record.curly_quote_raw}
          </Typography.Paragraph>
        ),
      });
    }
    if (record.error) {
      items.push({
        key: t('错误信息'),
        value: (
          <Typography.Text type='danger'>{record.error}</Typography.Text>
        ),
      });
    }
    if (items.length === 0) return null;
    return (
      <Descriptions
        data={items}
        row
        size='small'
        style={{ padding: '8px 16px' }}
      />
    );
  };

  const passCount = results.filter((r) => r.authentic).length;
  const failCount = results.filter((r) => !r.authentic && !r.error).length;
  const errCount = results.filter((r) => r.error).length;

  return (
    <Modal
      title={t('Claude 指纹检测结果')}
      visible={showFingerprintModal}
      onCancel={() => setShowFingerprintModal(false)}
      width={900}
      centered
      footer={null}
      bodyStyle={{ padding: '12px 24px 24px' }}
    >
      {results.length > 0 && (
        <div className='flex gap-3 mb-3'>
          <Tag color='green' size='large'>
            {t('正品')}: {passCount}
          </Tag>
          <Tag color='red' size='large'>
            {t('异常')}: {failCount}
          </Tag>
          {errCount > 0 && (
            <Tag color='orange' size='large'>
              {t('错误')}: {errCount}
            </Tag>
          )}
        </div>
      )}
      <Table
        columns={columns}
        dataSource={results}
        rowKey='channel_id'
        expandedRowRender={expandRowRender}
        loading={fingerprintLoading}
        pagination={
          results.length > 10 ? { pageSize: 10 } : false
        }
        size='small'
        empty={
          <Typography.Text type='tertiary'>
            {t('暂无检测结果')}
          </Typography.Text>
        }
      />
    </Modal>
  );
};

export default FingerprintResultModal;
