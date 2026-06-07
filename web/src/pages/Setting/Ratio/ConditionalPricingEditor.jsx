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
  Select,
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

const TYPE_OPTIONS = [
  { value: 'header', label: 'header（请求头）' },
  { value: 'param', label: 'param（请求体 JSON 路径）' },
  { value: 'time', label: 'time（时段）' },
];

const MATCH_OPTIONS = [
  { value: 'contains', label: 'contains（包含）' },
  { value: 'equals', label: 'equals（相等）' },
  { value: 'prefix', label: 'prefix（前缀）' },
  { value: 'exists', label: 'exists（存在）' },
];

const WEEKDAY_OPTIONS = [
  { value: 0, label: '周日' },
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
];

export default function ConditionalPricingEditor(props) {
  const { t } = useTranslation();
  const [models, setModels] = useState([]);
  const [visible, setVisible] = useState(false);
  const [ruleModalVisible, setRuleModalVisible] = useState(false);
  const [isEditMode, setIsEditMode] = useState(false);
  const [currentModel, setCurrentModel] = useState(null);
  const [currentRule, setCurrentRule] = useState(null);
  const [currentRuleIndex, setCurrentRuleIndex] = useState(-1);
  const [searchText, setSearchText] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const pageSize = 10;

  useEffect(() => {
    try {
      const cfg = JSON.parse(props.options.ConditionalPricing || '{}');
      const modelData = Object.entries(cfg).map(([name, c]) => ({
        name,
        enabled: c.enabled || false,
        strategy: c.strategy || 'first-match',
        rules: c.rules || [],
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
          strategy: model.strategy || 'first-match',
          rules: model.rules,
        };
      });

      const res = await API.put('/api/option/', {
        key: 'ConditionalPricing',
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

  const formatRule = (rule) => {
    if (rule.type === 'header') {
      return `header ${rule.key} ${rule.match || 'contains'} "${rule.value || ''}"`;
    }
    if (rule.type === 'param') {
      return `param ${rule.key} ${rule.match || 'contains'} "${rule.value || ''}"`;
    }
    if (rule.type === 'time') {
      const tz = rule.timezone || 'UTC';
      const hours =
        rule.start_hour !== rule.end_hour
          ? `${rule.start_hour}:00-${rule.end_hour}:00`
          : '全天';
      const wd =
        Array.isArray(rule.weekdays) && rule.weekdays.length > 0
          ? ` 周${rule.weekdays.join(',')}`
          : '';
      return `time ${tz} ${hours}${wd}`;
    }
    return rule.type;
  };

  const columns = [
    {
      title: t('模型名称'),
      dataIndex: 'name',
      render: (text) => (
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
      width: 90,
      render: (enabled, record) => (
        <Switch
          checked={enabled}
          onChange={(checked) => updateModelEnabled(record.name, checked)}
        />
      ),
    },
    {
      title: t('命中策略'),
      dataIndex: 'strategy',
      width: 120,
      render: (s) => <Tag color='grey'>{s || 'first-match'}</Tag>,
    },
    {
      title: t('条件规则'),
      dataIndex: 'rules',
      render: (rules) => (
        <Space wrap>
          {rules.length === 0 ? (
            <Text type='tertiary'>{t('未配置')}</Text>
          ) : (
            rules.map((rule, index) => (
              <Tag color='green' key={index}>
                {(rule.name ? rule.name + ': ' : '') + formatRule(rule)} ×{rule.multiplier}
              </Tag>
            ))
          )}
        </Space>
      ),
    },
    {
      title: t('操作'),
      width: 150,
      render: (_, record) => (
        <Space>
          <Button
            type='primary'
            icon={<IconEdit />}
            size='small'
            onClick={() => editModel(record)}
          />
          <Button icon={<IconCopy />} size='small' onClick={() => copyModel(record)} />
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

  const ruleColumns = [
    { title: t('标识'), dataIndex: 'name', render: (v) => v || '-' },
    { title: t('类型'), dataIndex: 'type', width: 80 },
    { title: t('条件'), render: (_, record) => formatRule(record) },
    {
      title: t('乘数'),
      dataIndex: 'multiplier',
      width: 80,
      render: (v) => `×${v}`,
    },
    {
      title: t('操作'),
      width: 100,
      render: (_, record, index) => (
        <Space>
          <Button icon={<IconEdit />} size='small' onClick={() => editRule(index)} />
          <Button
            icon={<IconDelete />}
            type='danger'
            size='small'
            onClick={() => deleteRule(index)}
          />
        </Space>
      ),
    },
  ];

  const updateModelEnabled = (name, enabled) => {
    setModels((prev) =>
      prev.map((m) => (m.name === name ? { ...m, enabled } : m))
    );
  };

  const deleteModel = (name) => {
    setModels((prev) => prev.filter((m) => m.name !== name));
  };

  const copyModel = (record) => {
    setCurrentModel({
      name: record.name + '-copy',
      enabled: record.enabled,
      strategy: record.strategy,
      rules: JSON.parse(JSON.stringify(record.rules)),
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
    setCurrentModel({ name: '', enabled: true, strategy: 'first-match', rules: [] });
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
    if (currentModel.rules.length === 0) {
      showWarning(t('请至少添加一条条件规则'));
      return;
    }
    if (isEditMode) {
      setModels((prev) =>
        prev.map((m) => (m.name === currentModel.name ? currentModel : m))
      );
    } else {
      setModels((prev) => [currentModel, ...prev]);
    }
    setVisible(false);
    setCurrentModel(null);
  };

  const addRule = () => {
    setCurrentRule({
      name: '',
      type: 'header',
      key: 'anthropic-beta',
      match: 'contains',
      value: 'fast-mode',
      timezone: 'Asia/Shanghai',
      start_hour: 0,
      end_hour: 8,
      weekdays: [],
      multiplier: 1.5,
    });
    setCurrentRuleIndex(-1);
    setRuleModalVisible(true);
  };

  const editRule = (index) => {
    setCurrentRule({ ...currentModel.rules[index] });
    setCurrentRuleIndex(index);
    setRuleModalVisible(true);
  };

  const deleteRule = (index) => {
    setCurrentModel((prev) => ({
      ...prev,
      rules: prev.rules.filter((_, i) => i !== index),
    }));
  };

  const saveRule = () => {
    if (!currentRule.multiplier || currentRule.multiplier <= 0) {
      showError(t('乘数必须大于 0'));
      return;
    }
    if (
      (currentRule.type === 'header' || currentRule.type === 'param') &&
      !currentRule.key
    ) {
      showError(t('请填写 header 名称或 param 路径'));
      return;
    }
    // Strip unrelated fields per type to keep JSON clean
    let cleaned = { name: currentRule.name, type: currentRule.type, multiplier: currentRule.multiplier };
    if (currentRule.type === 'header' || currentRule.type === 'param') {
      cleaned.key = currentRule.key;
      cleaned.match = currentRule.match || 'contains';
      if (cleaned.match !== 'exists') cleaned.value = currentRule.value || '';
    } else if (currentRule.type === 'time') {
      cleaned.timezone = currentRule.timezone || 'UTC';
      cleaned.start_hour = currentRule.start_hour || 0;
      cleaned.end_hour = currentRule.end_hour || 0;
      if (Array.isArray(currentRule.weekdays) && currentRule.weekdays.length > 0) {
        cleaned.weekdays = currentRule.weekdays;
      }
    }

    let newRules;
    if (currentRuleIndex === -1) {
      newRules = [...currentModel.rules, cleaned];
    } else {
      newRules = currentModel.rules.map((r, i) =>
        i === currentRuleIndex ? cleaned : r
      );
    }
    setCurrentModel((prev) => ({ ...prev, rules: newRules }));
    setRuleModalVisible(false);
    setCurrentRule(null);
  };

  return (
    <>
      <Space vertical align='start' style={{ width: '100%' }}>
        <Space className='mt-2'>
          <Button icon={<IconPlus />} onClick={addNewModel}>
            {t('添加模型')}
          </Button>
          <Button type='primary' icon={<IconSave />} loading={loading} onClick={submitData}>
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
            title={t('暂无条件计费配置')}
            description={t('点击「添加模型」按钮创建条件计费规则（时段 / 请求头 / 请求体）')}
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
        title={isEditMode ? t('编辑条件计费') : t('添加条件计费')}
        visible={visible}
        onCancel={() => {
          setVisible(false);
          setCurrentModel(null);
        }}
        onOk={saveModel}
        width={820}
        style={{ maxHeight: '80vh' }}
      >
        {currentModel && (
          <Space vertical align='start' style={{ width: '100%' }}>
            <Form labelPosition='left' labelWidth={100}>
              <Form.Input
                field='name'
                label={t('模型名称')}
                placeholder={t('例如: claude-sonnet-4-6 或 claude-*')}
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
              <Form.Select
                field='strategy'
                label={t('命中策略')}
                value={currentModel.strategy}
                onChange={(value) =>
                  setCurrentModel((prev) => ({ ...prev, strategy: value }))
                }
                optionList={[
                  { value: 'first-match', label: 'first-match（第一条命中生效）' },
                  { value: 'multiply-all', label: 'multiply-all（所有命中连乘）' },
                ]}
              />
            </Form>

            <Card
              title={t('条件规则（按顺序匹配）')}
              headerExtraContent={
                <Button icon={<IconPlus />} size='small' onClick={addRule}>
                  {t('添加规则')}
                </Button>
              }
              style={{ width: '100%' }}
            >
              {currentModel.rules.length === 0 ? (
                <Empty
                  title={t('暂无条件规则')}
                  description={t('点击「添加规则」按钮配置')}
                />
              ) : (
                <Table
                  columns={ruleColumns}
                  dataSource={currentModel.rules}
                  rowKey={(_, index) => index}
                  pagination={false}
                  size='small'
                />
              )}
            </Card>

            <Card title={t('配置说明')} style={{ width: '100%' }}>
              <Text type='tertiary'>
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  <li>{t('header：从请求头读取，如 anthropic-beta 含 fast-mode 加价')}</li>
                  <li>{t('param：从请求体 JSON 路径读取，如 service_tier == priority')}</li>
                  <li>{t('time：按时区 + 小时区间 [start,end) 和/或 星期集合，如夜间 0-8 点折扣')}</li>
                  <li>{t('命中后将乘数乘到最终计费上；first-match 取第一条命中，multiply-all 连乘')}</li>
                  <li>{t('支持通配符模型名；命中乘数与字段取值会写入对账快照')}</li>
                </ul>
              </Text>
            </Card>
          </Space>
        )}
      </Modal>

      {/* 规则编辑弹窗 */}
      <Modal
        title={currentRuleIndex === -1 ? t('添加条件规则') : t('编辑条件规则')}
        visible={ruleModalVisible}
        onCancel={() => {
          setRuleModalVisible(false);
          setCurrentRule(null);
        }}
        onOk={saveRule}
      >
        {currentRule && (
          <Form labelPosition='left' labelWidth={120}>
            <Form.Input
              field='name'
              label={t('规则标识')}
              value={currentRule.name}
              placeholder={t('如 fast-mode / night-discount（写入快照）')}
              onChange={(value) =>
                setCurrentRule((prev) => ({ ...prev, name: value }))
              }
            />
            <Form.Select
              field='type'
              label={t('条件类型')}
              value={currentRule.type}
              optionList={TYPE_OPTIONS}
              onChange={(value) =>
                setCurrentRule((prev) => ({ ...prev, type: value }))
              }
            />

            {(currentRule.type === 'header' || currentRule.type === 'param') && (
              <>
                <Form.Input
                  field='key'
                  label={currentRule.type === 'header' ? t('Header 名称') : t('JSON 路径')}
                  value={currentRule.key}
                  placeholder={
                    currentRule.type === 'header' ? 'anthropic-beta' : 'service_tier'
                  }
                  onChange={(value) =>
                    setCurrentRule((prev) => ({ ...prev, key: value }))
                  }
                />
                <Form.Select
                  field='match'
                  label={t('匹配方式')}
                  value={currentRule.match}
                  optionList={MATCH_OPTIONS}
                  onChange={(value) =>
                    setCurrentRule((prev) => ({ ...prev, match: value }))
                  }
                />
                {currentRule.match !== 'exists' && (
                  <Form.Input
                    field='value'
                    label={t('期望值')}
                    value={currentRule.value}
                    placeholder='fast-mode / priority'
                    onChange={(value) =>
                      setCurrentRule((prev) => ({ ...prev, value }))
                    }
                  />
                )}
              </>
            )}

            {currentRule.type === 'time' && (
              <>
                <Form.Input
                  field='timezone'
                  label={t('时区')}
                  value={currentRule.timezone}
                  placeholder='Asia/Shanghai'
                  onChange={(value) =>
                    setCurrentRule((prev) => ({ ...prev, timezone: value }))
                  }
                />
                <Form.InputNumber
                  field='start_hour'
                  label={t('起始小时')}
                  value={currentRule.start_hour}
                  min={0}
                  max={24}
                  onChange={(value) =>
                    setCurrentRule((prev) => ({ ...prev, start_hour: value }))
                  }
                  extraText={t('小时区间 [start, end)；start==end 表示不限制小时，end<start 表示跨夜')}
                />
                <Form.InputNumber
                  field='end_hour'
                  label={t('结束小时')}
                  value={currentRule.end_hour}
                  min={0}
                  max={24}
                  onChange={(value) =>
                    setCurrentRule((prev) => ({ ...prev, end_hour: value }))
                  }
                />
                <Form.Select
                  field='weekdays'
                  label={t('星期（可多选）')}
                  multiple
                  value={currentRule.weekdays}
                  optionList={WEEKDAY_OPTIONS}
                  placeholder={t('留空表示不限制星期')}
                  onChange={(value) =>
                    setCurrentRule((prev) => ({ ...prev, weekdays: value }))
                  }
                />
              </>
            )}

            <Form.InputNumber
              field='multiplier'
              label={t('乘数')}
              value={currentRule.multiplier}
              min={0}
              precision={4}
              onChange={(value) =>
                setCurrentRule((prev) => ({ ...prev, multiplier: value }))
              }
              extraText={t('命中后乘到价格上，如 6 表示 6 倍、0.5 表示 5 折')}
            />
          </Form>
        )}
      </Modal>
    </>
  );
}
