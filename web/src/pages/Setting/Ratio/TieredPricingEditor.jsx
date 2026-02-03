/*
Copyright (C) 2025 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/

import React, { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Input,
  InputNumber,
  Modal,
  Form,
  Space,
  Switch,
  Card,
  Typography,
  Popconfirm,
  Tag,
  Empty,
  Tooltip,
} from '@douyinfe/semi-ui';
import {
  IconDelete,
  IconPlus,
  IconSearch,
  IconSave,
  IconEdit,
  IconCopy,
} from '@douyinfe/semi-icons';
import { API, showError, showSuccess, showWarning } from '../../../helpers';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

export default function TieredPricingEditor(props) {
  const { t } = useTranslation();
  const [models, setModels] = useState([]);
  const [visible, setVisible] = useState(false);
  const [tierModalVisible, setTierModalVisible] = useState(false);
  const [isEditMode, setIsEditMode] = useState(false);
  const [currentModel, setCurrentModel] = useState(null);
  const [currentTier, setCurrentTier] = useState(null);
  const [currentTierIndex, setCurrentTierIndex] = useState(-1);
  const [searchText, setSearchText] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const pageSize = 10;

  useEffect(() => {
    try {
      const tieredPricing = JSON.parse(props.options.TieredPricing || '{}');

      const modelData = Object.entries(tieredPricing).map(([name, config]) => ({
        name,
        enabled: config.enabled || false,
        tiers: config.tiers || [],
      }));

      setModels(modelData);
    } catch (error) {
      console.error('JSON解析错误:', error);
      setModels([]);
    }
  }, [props.options]);

  const filteredModels = models.filter((model) =>
    searchText ? model.name.toLowerCase().includes(searchText.toLowerCase()) : true
  );

  const getPagedData = (data, page, size) => {
    const start = (page - 1) * size;
    return data.slice(start, start + size);
  };

  const pagedData = getPagedData(filteredModels, currentPage, pageSize);

  const submitData = async () => {
    setLoading(true);
    try {
      const output = {};
      models.forEach((model) => {
        output[model.name] = {
          enabled: model.enabled,
          tiers: model.tiers,
        };
      });

      const res = await API.put('/api/option/', {
        key: 'TieredPricing',
        value: JSON.stringify(output, null, 2),
      });

      if (res.data.success) {
        showSuccess(t('保存成功'));
        props.refresh();
      } else {
        showError(res.data.message);
      }
    } catch (error) {
      console.error('保存失败:', error);
      showError(t('保存失败，请重试'));
    } finally {
      setLoading(false);
    }
  };

  const formatTierRange = (tier) => {
    const max = tier.max_tokens === -1 ? '∞' : tier.max_tokens;
    return `${tier.min_tokens}K - ${max}K`;
  };

  const columns = [
    {
      title: t('模型名称'),
      dataIndex: 'name',
      key: 'name',
      render: (text, record) => (
        <Space>
          <Text strong>{text}</Text>
          {text.includes('*') && (
            <Tag color='blue' size='small'>
              {t('通配符')}
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: t('状态'),
      dataIndex: 'enabled',
      key: 'enabled',
      width: 100,
      render: (enabled, record) => (
        <Switch
          checked={enabled}
          onChange={(checked) => updateModelEnabled(record.name, checked)}
        />
      ),
    },
    {
      title: t('价格区间'),
      dataIndex: 'tiers',
      key: 'tiers',
      render: (tiers) => (
        <Space wrap>
          {tiers.length === 0 ? (
            <Text type='tertiary'>{t('未配置')}</Text>
          ) : (
            tiers.map((tier, index) => (
              <Tooltip
                key={index}
                content={
                  <div>
                    <div>{t('输入价格')}: ${tier.input_price}/M</div>
                    <div>{t('输出价格')}: ${tier.output_price}/M</div>
                    <div>{t('缓存命中')}: ${tier.cache_hit_price}/M</div>
                    {tier.cache_store_price > 0 && (
                      <div>{t('缓存存储')}: ${tier.cache_store_price}/M/h</div>
                    )}
                  </div>
                }
              >
                <Tag color='green'>{formatTierRange(tier)}</Tag>
              </Tooltip>
            ))
          )}
        </Space>
      ),
    },
    {
      title: t('操作'),
      key: 'action',
      width: 150,
      render: (_, record) => (
        <Space>
          <Button
            type='primary'
            icon={<IconEdit />}
            size='small'
            onClick={() => editModel(record)}
          />
          <Button
            icon={<IconCopy />}
            size='small'
            onClick={() => copyModel(record)}
          />
          <Popconfirm
            title={t('确定删除此模型配置？')}
            onConfirm={() => deleteModel(record.name)}
          >
            <Button icon={<IconDelete />} type='danger' size='small' />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const tierColumns = [
    {
      title: t('Token 范围 (千)'),
      key: 'range',
      render: (_, record) => formatTierRange(record),
    },
    {
      title: t('输入价格'),
      dataIndex: 'input_price',
      key: 'input_price',
      render: (price) => `$${price}/M`,
    },
    {
      title: t('输出价格'),
      dataIndex: 'output_price',
      key: 'output_price',
      render: (price) => `$${price}/M`,
    },
    {
      title: t('缓存命中'),
      dataIndex: 'cache_hit_price',
      key: 'cache_hit_price',
      render: (price) => `$${price}/M`,
    },
    {
      title: t('缓存存储'),
      dataIndex: 'cache_store_price',
      key: 'cache_store_price',
      render: (price) => (price > 0 ? `$${price}/M/h` : '-'),
    },
    {
      title: t('操作'),
      key: 'action',
      width: 100,
      render: (_, record, index) => (
        <Space>
          <Button
            icon={<IconEdit />}
            size='small'
            onClick={() => editTier(index)}
          />
          <Button
            icon={<IconDelete />}
            type='danger'
            size='small'
            onClick={() => deleteTier(index)}
          />
        </Space>
      ),
    },
  ];

  const updateModelEnabled = (name, enabled) => {
    setModels((prev) =>
      prev.map((model) =>
        model.name === name ? { ...model, enabled } : model
      )
    );
  };

  const deleteModel = (name) => {
    setModels((prev) => prev.filter((model) => model.name !== name));
  };

  const copyModel = (record) => {
    setCurrentModel({
      name: record.name + '-copy',
      enabled: record.enabled,
      tiers: JSON.parse(JSON.stringify(record.tiers)),
    });
    setIsEditMode(false);
    setVisible(true);
  };

  const editModel = (record) => {
    setCurrentModel(JSON.parse(JSON.stringify(record)));
    setIsEditMode(true);
    setVisible(true);
  };

  const addNewModel = () => {
    setCurrentModel({
      name: '',
      enabled: true,
      tiers: [],
    });
    setIsEditMode(false);
    setVisible(true);
  };

  const saveModel = () => {
    if (!currentModel.name) {
      showError(t('请输入模型名称'));
      return;
    }

    if (!isEditMode && models.some((m) => m.name === currentModel.name)) {
      showError(t('模型名称已存在'));
      return;
    }

    if (currentModel.tiers.length === 0) {
      showWarning(t('请至少添加一个价格区间'));
      return;
    }

    if (isEditMode) {
      setModels((prev) =>
        prev.map((model) =>
          model.name === currentModel.name ? currentModel : model
        )
      );
    } else {
      setModels((prev) => [currentModel, ...prev]);
    }

    setVisible(false);
    setCurrentModel(null);
  };

  const addTier = () => {
    const lastTier = currentModel.tiers[currentModel.tiers.length - 1];
    setCurrentTier({
      min_tokens: lastTier ? lastTier.max_tokens : 0,
      max_tokens: -1,
      input_price: 0.25,
      output_price: 2.0,
      cache_hit_price: 0.05,
      cache_store_price: 0,
    });
    setCurrentTierIndex(-1);
    setTierModalVisible(true);
  };

  const editTier = (index) => {
    setCurrentTier({ ...currentModel.tiers[index] });
    setCurrentTierIndex(index);
    setTierModalVisible(true);
  };

  const deleteTier = (index) => {
    setCurrentModel((prev) => ({
      ...prev,
      tiers: prev.tiers.filter((_, i) => i !== index),
    }));
  };

  const saveTier = () => {
    if (currentTier.min_tokens < 0) {
      showError(t('最小 Token 数不能为负'));
      return;
    }

    if (currentTier.max_tokens !== -1 && currentTier.max_tokens <= currentTier.min_tokens) {
      showError(t('最大 Token 数必须大于最小值，或设为 -1 表示无上限'));
      return;
    }

    let newTiers;
    if (currentTierIndex === -1) {
      newTiers = [...currentModel.tiers, currentTier];
    } else {
      newTiers = currentModel.tiers.map((tier, i) =>
        i === currentTierIndex ? currentTier : tier
      );
    }

    // Sort tiers by min_tokens
    newTiers.sort((a, b) => a.min_tokens - b.min_tokens);

    setCurrentModel((prev) => ({
      ...prev,
      tiers: newTiers,
    }));

    setTierModalVisible(false);
    setCurrentTier(null);
  };

  return (
    <>
      <Space vertical align='start' style={{ width: '100%' }}>
        <Space className='mt-2'>
          <Button icon={<IconPlus />} onClick={addNewModel}>
            {t('添加模型')}
          </Button>
          <Button
            type='primary'
            icon={<IconSave />}
            loading={loading}
            onClick={submitData}
          >
            {t('保存配置')}
          </Button>
          <Input
            prefix={<IconSearch />}
            placeholder={t('搜索模型名称')}
            value={searchText}
            onChange={(value) => {
              setSearchText(value);
              setCurrentPage(1);
            }}
            style={{ width: 200 }}
            showClear
          />
        </Space>

        {models.length === 0 ? (
          <Empty
            title={t('暂无分段价格配置')}
            description={t('点击「添加模型」按钮创建分段价格配置')}
            style={{ marginTop: 40 }}
          />
        ) : (
          <Table
            columns={columns}
            dataSource={pagedData}
            rowKey='name'
            pagination={{
              currentPage,
              pageSize,
              total: filteredModels.length,
              onPageChange: setCurrentPage,
              showTotal: true,
            }}
          />
        )}
      </Space>

      {/* 模型编辑弹窗 */}
      <Modal
        title={isEditMode ? t('编辑分段价格') : t('添加分段价格')}
        visible={visible}
        onCancel={() => {
          setVisible(false);
          setCurrentModel(null);
        }}
        onOk={saveModel}
        width={800}
        style={{ maxHeight: '80vh' }}
      >
        {currentModel && (
          <Space vertical align='start' style={{ width: '100%' }}>
            <Form labelPosition='left' labelWidth={100}>
              <Form.Input
                field='name'
                label={t('模型名称')}
                placeholder={t('例如: doubao-seed-1.6 或 doubao-seed-*')}
                value={currentModel.name}
                disabled={isEditMode}
                onChange={(value) =>
                  setCurrentModel((prev) => ({ ...prev, name: value }))
                }
              />
              <Form.Switch
                field='enabled'
                label={t('启用')}
                checked={currentModel.enabled}
                onChange={(checked) =>
                  setCurrentModel((prev) => ({ ...prev, enabled: checked }))
                }
              />
            </Form>

            <Card
              title={t('价格区间配置')}
              headerExtraContent={
                <Button icon={<IconPlus />} size='small' onClick={addTier}>
                  {t('添加区间')}
                </Button>
              }
              style={{ width: '100%' }}
            >
              {currentModel.tiers.length === 0 ? (
                <Empty
                  title={t('暂无价格区间')}
                  description={t('点击「添加区间」按钮配置价格')}
                />
              ) : (
                <Table
                  columns={tierColumns}
                  dataSource={currentModel.tiers}
                  rowKey={(_, index) => index}
                  pagination={false}
                  size='small'
                />
              )}
            </Card>

            <Card title={t('配置说明')} style={{ width: '100%' }}>
              <Text type='tertiary'>
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  <li>{t('Token 范围单位为「千 tokens」，例如 128 表示 128K tokens')}</li>
                  <li>{t('max_tokens 设为 -1 表示无上限')}</li>
                  <li>{t('价格单位为 USD/百万 tokens')}</li>
                  <li>{t('支持通配符，例如 doubao-seed-* 匹配所有 doubao-seed- 开头的模型')}</li>
                  <li>{t('分段价格优先级高于模型倍率和固定价格')}</li>
                </ul>
              </Text>
            </Card>
          </Space>
        )}
      </Modal>

      {/* 价格区间编辑弹窗 */}
      <Modal
        title={currentTierIndex === -1 ? t('添加价格区间') : t('编辑价格区间')}
        visible={tierModalVisible}
        onCancel={() => {
          setTierModalVisible(false);
          setCurrentTier(null);
        }}
        onOk={saveTier}
      >
        {currentTier && (
          <Form labelPosition='left' labelWidth={120}>
            <Form.InputNumber
              field='min_tokens'
              label={t('最小 Token (千)')}
              value={currentTier.min_tokens}
              min={0}
              onChange={(value) =>
                setCurrentTier((prev) => ({ ...prev, min_tokens: value }))
              }
              suffix='K'
            />
            <Form.InputNumber
              field='max_tokens'
              label={t('最大 Token (千)')}
              value={currentTier.max_tokens}
              min={-1}
              onChange={(value) =>
                setCurrentTier((prev) => ({ ...prev, max_tokens: value }))
              }
              suffix='K'
              extraText={t('-1 表示无上限')}
            />
            <Form.InputNumber
              field='input_price'
              label={t('输入价格')}
              value={currentTier.input_price}
              min={0}
              precision={4}
              onChange={(value) =>
                setCurrentTier((prev) => ({ ...prev, input_price: value }))
              }
              suffix='$/M tokens'
            />
            <Form.InputNumber
              field='output_price'
              label={t('输出价格')}
              value={currentTier.output_price}
              min={0}
              precision={4}
              onChange={(value) =>
                setCurrentTier((prev) => ({ ...prev, output_price: value }))
              }
              suffix='$/M tokens'
            />
            <Form.InputNumber
              field='cache_hit_price'
              label={t('缓存命中价格')}
              value={currentTier.cache_hit_price}
              min={0}
              precision={4}
              onChange={(value) =>
                setCurrentTier((prev) => ({ ...prev, cache_hit_price: value }))
              }
              suffix='$/M tokens'
            />
            <Form.InputNumber
              field='cache_store_price'
              label={t('缓存存储价格')}
              value={currentTier.cache_store_price}
              min={0}
              precision={4}
              onChange={(value) =>
                setCurrentTier((prev) => ({ ...prev, cache_store_price: value }))
              }
              suffix='$/M tokens/h'
              extraText={t('可选，设为 0 表示不计费')}
            />
          </Form>
        )}
      </Modal>
    </>
  );
}
