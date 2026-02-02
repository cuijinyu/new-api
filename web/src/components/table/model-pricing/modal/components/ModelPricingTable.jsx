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

import React from 'react';
import { Card, Avatar, Typography, Table, Tag, Collapsible } from '@douyinfe/semi-ui';
import { IconCoinMoneyStroked, IconChevronDown } from '@douyinfe/semi-icons';
import { calculateModelPrice } from '../../../../../helpers';

const { Text } = Typography;

// 格式化分段区间显示
const formatTierRange = (minTokens, maxTokens, t) => {
  if (maxTokens === -1) {
    return `≥${minTokens}K`;
  }
  return `${minTokens}K - ${maxTokens}K`;
};

const ModelPricingTable = ({
  modelData,
  groupRatio,
  currency,
  tokenUnit,
  displayPrice,
  showRatio,
  usableGroup,
  autoGroups = [],
  isAdminUser = false,
  t,
}) => {
  // 非管理员用户不显示分组价格表
  if (!isAdminUser) {
    return null;
  }
  const modelEnableGroups = Array.isArray(modelData?.enable_groups)
    ? modelData.enable_groups
    : [];
  const autoChain = autoGroups.filter((g) => modelEnableGroups.includes(g));

  // 检查是否启用分段计费
  const isTieredPricing = modelData?.tiered_pricing_enabled && 
    Array.isArray(modelData?.tiered_pricing) && 
    modelData.tiered_pricing.length > 0;

  // 渲染分段计费表格
  const renderTieredPricingTable = () => {
    if (!isTieredPricing) return null;

    const priceData = calculateModelPrice({
      record: modelData,
      selectedGroup: 'all',
      groupRatio,
      tokenUnit,
      displayPrice,
      currency,
    });

    if (!priceData.tieredPrices) return null;

    const tableData = priceData.tieredPrices.map((tier, index) => ({
      key: index,
      range: formatTierRange(tier.minTokens, tier.maxTokens, t),
      inputPrice: tier.inputPrice,
      outputPrice: tier.outputPrice,
      cacheHitPrice: tier.cacheHitPrice,
    }));

    const columns = [
      {
        title: t('Token 区间'),
        dataIndex: 'range',
        render: (text) => (
          <Tag color='blue' size='small' shape='circle'>
            {text}
          </Tag>
        ),
      },
      {
        title: t('输入价格'),
        dataIndex: 'inputPrice',
        render: (text) => (
          <>
            <div className='font-semibold text-orange-600'>{text}</div>
            <div className='text-xs text-gray-500'>
              / {tokenUnit === 'K' ? '1K' : '1M'} tokens
            </div>
          </>
        ),
      },
      {
        title: t('输出价格'),
        dataIndex: 'outputPrice',
        render: (text) => (
          <>
            <div className='font-semibold text-orange-600'>{text}</div>
            <div className='text-xs text-gray-500'>
              / {tokenUnit === 'K' ? '1K' : '1M'} tokens
            </div>
          </>
        ),
      },
    ];

    // 如果有缓存命中价格，添加该列
    const hasCachePrice = tableData.some((row) => row.cacheHitPrice);
    if (hasCachePrice) {
      columns.push({
        title: t('缓存命中'),
        dataIndex: 'cacheHitPrice',
        render: (text) => (
          text ? (
            <>
              <div className='font-semibold text-green-600'>{text}</div>
              <div className='text-xs text-gray-500'>
                / {tokenUnit === 'K' ? '1K' : '1M'} tokens
              </div>
            </>
          ) : '-'
        ),
      });
    }

    return (
      <div className='mb-4'>
        <div className='flex items-center gap-2 mb-2'>
          <Tag color='cyan' size='small'>
            {t('分段计费')}
          </Tag>
          <span className='text-xs text-gray-500'>
            {t('根据输入 Token 长度分段计价')}
          </span>
        </div>
        <Table
          dataSource={tableData}
          columns={columns}
          pagination={false}
          size='small'
          bordered={false}
          className='!rounded-lg'
        />
      </div>
    );
  };

  const renderGroupPriceTable = () => {
    // 仅展示模型可用的分组：模型 enable_groups 与用户可用分组的交集

    const availableGroups = Object.keys(usableGroup || {})
      .filter((g) => g !== '')
      .filter((g) => g !== 'auto')
      .filter((g) => modelEnableGroups.includes(g));

    // 准备表格数据
    const tableData = availableGroups.map((group) => {
      const priceData = modelData
        ? calculateModelPrice({
            record: modelData,
            selectedGroup: group,
            groupRatio,
            tokenUnit,
            displayPrice,
            currency,
          })
        : { inputPrice: '-', outputPrice: '-', price: '-' };

      // 获取分组倍率
      const groupRatioValue =
        groupRatio && groupRatio[group] ? groupRatio[group] : 1;

      // 确定计费类型显示
      let billingType = '-';
      if (isTieredPricing) {
        billingType = t('分段计费');
      } else if (modelData?.quota_type === 0) {
        billingType = t('按量计费');
      } else if (modelData?.quota_type === 1) {
        billingType = t('按次计费');
      }

      return {
        key: group,
        group: group,
        ratio: groupRatioValue,
        billingType,
        inputPrice: modelData?.quota_type === 0 ? priceData.inputPrice : '-',
        outputPrice:
          modelData?.quota_type === 0
            ? priceData.completionPrice || priceData.outputPrice
            : '-',
        fixedPrice: modelData?.quota_type === 1 ? priceData.price : '-',
        isTieredPricing: priceData.isTieredPricing,
      };
    });

    // 定义表格列
    const columns = [
      {
        title: t('分组'),
        dataIndex: 'group',
        render: (text) => (
          <Tag color='white' size='small' shape='circle'>
            {text}
            {t('分组')}
          </Tag>
        ),
      },
    ];

    // 如果显示倍率，添加倍率列
    if (showRatio) {
      columns.push({
        title: t('倍率'),
        dataIndex: 'ratio',
        render: (text) => (
          <Tag color='white' size='small' shape='circle'>
            {text}x
          </Tag>
        ),
      });
    }

    // 添加计费类型列
    columns.push({
      title: t('计费类型'),
      dataIndex: 'billingType',
      render: (text, record) => {
        let color = 'white';
        if (text === t('按量计费')) color = 'violet';
        else if (text === t('按次计费')) color = 'teal';
        else if (text === t('分段计费')) color = 'cyan';
        return (
          <Tag color={color} size='small' shape='circle'>
            {text || '-'}
          </Tag>
        );
      },
    });

    // 根据计费类型添加价格列
    if (isTieredPricing) {
      // 分段计费：显示提示查看上方分段表
      columns.push({
        title: t('价格'),
        dataIndex: 'inputPrice',
        render: (text, record) => (
          <span className='text-xs text-gray-500'>
            {t('详见上方分段价格表')}
          </span>
        ),
      });
    } else if (modelData?.quota_type === 0) {
      // 按量计费
      columns.push(
        {
          title: t('提示'),
          dataIndex: 'inputPrice',
          render: (text) => (
            <>
              <div className='font-semibold text-orange-600'>{text}</div>
              <div className='text-xs text-gray-500'>
                / {tokenUnit === 'K' ? '1K' : '1M'} tokens
              </div>
            </>
          ),
        },
        {
          title: t('补全'),
          dataIndex: 'outputPrice',
          render: (text) => (
            <>
              <div className='font-semibold text-orange-600'>{text}</div>
              <div className='text-xs text-gray-500'>
                / {tokenUnit === 'K' ? '1K' : '1M'} tokens
              </div>
            </>
          ),
        },
      );
    } else {
      // 按次计费
      columns.push({
        title: t('价格'),
        dataIndex: 'fixedPrice',
        render: (text) => (
          <>
            <div className='font-semibold text-orange-600'>{text}</div>
            <div className='text-xs text-gray-500'>/ 次</div>
          </>
        ),
      });
    }

    return (
      <Table
        dataSource={tableData}
        columns={columns}
        pagination={false}
        size='small'
        bordered={false}
        className='!rounded-lg'
      />
    );
  };

  return (
    <Card className='!rounded-2xl shadow-sm border-0'>
      <div className='flex items-center mb-4'>
        <Avatar size='small' color='orange' className='mr-2 shadow-md'>
          <IconCoinMoneyStroked size={16} />
        </Avatar>
        <div>
          <Text className='text-lg font-medium'>{t('分组价格')}</Text>
          <div className='text-xs text-gray-600'>
            {t('不同用户分组的价格信息')}
          </div>
        </div>
      </div>
      {autoChain.length > 0 && (
        <div className='flex flex-wrap items-center gap-1 mb-4'>
          <span className='text-sm text-gray-600'>{t('auto分组调用链路')}</span>
          <span className='text-sm'>→</span>
          {autoChain.map((g, idx) => (
            <React.Fragment key={g}>
              <Tag color='white' size='small' shape='circle'>
                {g}
                {t('分组')}
              </Tag>
              {idx < autoChain.length - 1 && <span className='text-sm'>→</span>}
            </React.Fragment>
          ))}
        </div>
      )}
      {renderTieredPricingTable()}
      {renderGroupPriceTable()}
    </Card>
  );
};

export default ModelPricingTable;
