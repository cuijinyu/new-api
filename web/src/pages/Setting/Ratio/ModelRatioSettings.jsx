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

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Banner,
  Button,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from '@douyinfe/semi-ui';
import {
  IconAlertTriangle,
  IconCopy,
  IconDelete,
  IconDownload,
  IconEdit,
  IconPlus,
  IconRefresh,
  IconSave,
  IconSearch,
  IconUpload,
} from '@douyinfe/semi-icons';
import {
  API,
  compareObjects,
  showError,
  showSuccess,
  showWarning,
  verifyJSON,
} from '../../../helpers';
import { useTranslation } from 'react-i18next';

const { Text, Title } = Typography;

const INITIAL_INPUTS = {
  ModelPrice: '',
  ModelRatio: '',
  CacheRatio: '',
  TieredPricing: '',
  ConditionalPricing: '',
  CompletionRatio: '',
  ImageRatio: '',
  ImageCompletionRatio: '',
  AudioRatio: '',
  AudioCompletionRatio: '',
  ExposeRatioEnabled: false,
};
const INITIAL_KEYS = Object.keys(INITIAL_INPUTS);

const BILLING_MODE_OPTIONS = [
  { label: '按量 Token 计费', value: 'ratio' },
  { label: '按次固定价', value: 'fixed' },
  { label: '分段计费', value: 'tiered' },
  { label: '条件计费', value: 'conditional' },
];

const CONDITION_TYPE_OPTIONS = [
  { label: 'Header 请求头', value: 'header' },
  { label: 'Param 请求体', value: 'param' },
  { label: 'Time 时段', value: 'time' },
];

const CONDITION_MATCH_OPTIONS = [
  { label: '包含 contains', value: 'contains' },
  { label: '等于 equals', value: 'equals' },
  { label: '前缀 prefix', value: 'prefix' },
  { label: '存在 exists', value: 'exists' },
];

const CONDITION_STRATEGY_OPTIONS = [
  { label: 'first-match：第一条命中生效', value: 'first-match' },
  { label: 'multiply-all：所有命中连乘', value: 'multiply-all' },
];

const WEEKDAY_OPTIONS = [
  { label: '周日', value: 0 },
  { label: '周一', value: 1 },
  { label: '周二', value: 2 },
  { label: '周三', value: 3 },
  { label: '周四', value: 4 },
  { label: '周五', value: 5 },
  { label: '周六', value: 6 },
];

const SIMPLE_JSON_KEYS = [
  'ModelPrice',
  'ModelRatio',
  'CacheRatio',
  'CompletionRatio',
  'ImageRatio',
  'ImageCompletionRatio',
  'AudioRatio',
  'AudioCompletionRatio',
];

const JSON_FIELD_META = [
  {
    key: 'ModelPrice',
    label: '模型固定价格',
    help: '按次计费价格，单位 USD/次。存在固定价格时，会覆盖模型倍率和补全倍率。',
    placeholder: '{"gpt-4-gizmo-*": 0.1}',
  },
  {
    key: 'ModelRatio',
    label: '模型倍率',
    help: '按量计费的输入倍率。换算约定：1 倍率 = 2 USD / 1M tokens。',
    placeholder: '{"gpt-4o-mini": 0.075}',
  },
  {
    key: 'CacheRatio',
    label: '提示缓存倍率',
    help: '缓存命中 tokens 的倍率，留空时按模型默认逻辑处理。',
    placeholder: '{"gpt-4o-mini": 0.25}',
  },
  {
    key: 'TieredPricing',
    label: '分段价格配置',
    help: '按输入 Token 长度分段计价，优先级高于模型倍率和固定价格。',
    placeholder:
      '{"doubao-seed-1.6": {"enabled": true, "tiers": [{"min_tokens": 0, "max_tokens": 128, "input_price": 0.25, "output_price": 2}]}}',
  },
  {
    key: 'ConditionalPricing',
    label: '条件计费配置',
    help: '根据 header、请求参数或时间命中倍率，通常用于活动价、客户专属价或时段价。',
    placeholder:
      '{"gpt-4o-mini": {"enabled": true, "strategy": "first-match", "rules": []}}',
  },
  {
    key: 'CompletionRatio',
    label: '模型补全倍率',
    help: '输出价格相对于输入价格的乘数，仅对自定义模型有效。',
    placeholder: '{"gpt-4o-mini": 4}',
  },
  {
    key: 'ImageRatio',
    label: '图片输入倍率',
    help: '图片输入 tokens 的独立倍率，仅部分模型支持。',
    placeholder: '{"gpt-image-1": 2}',
  },
  {
    key: 'ImageCompletionRatio',
    label: '图片输出补全倍率',
    help: '图片输出 tokens 的独立倍率，常用于 Gemini 生图模型文本/图片分开计费。',
    placeholder: '{"gemini-2.5-flash-image": 4.27}',
  },
  {
    key: 'AudioRatio',
    label: '音频输入倍率',
    help: '音频输入 tokens 的独立倍率，仅部分模型支持。',
    placeholder: '{"gpt-4o-audio-preview": 16}',
  },
  {
    key: 'AudioCompletionRatio',
    label: '音频输出补全倍率',
    help: '音频输出 tokens 的独立倍率，仅部分模型支持。',
    placeholder: '{"gpt-4o-realtime": 2}',
  },
];

function safeParseJSON(value, fallback = {}) {
  if (value === undefined || value === null || value === '') return fallback;
  try {
    return JSON.parse(value);
  } catch (error) {
    return fallback;
  }
}

function parseJSONWithError(value, key) {
  if (!value || !String(value).trim()) return { data: {}, error: null };
  try {
    return { data: JSON.parse(value), error: null };
  } catch (error) {
    return { data: {}, error: `${key}: ${error.message}` };
  }
}

function isBlank(value) {
  return value === undefined || value === null || value === '';
}

function numberOrBlank(value) {
  if (isBlank(value)) return '';
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : value;
}

function numberValue(value, fallback = 0) {
  if (isBlank(value)) return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function hasValue(value) {
  return value !== '' && value !== undefined && value !== null;
}

function inferBillingMode(row) {
  if (!row) return 'ratio';
  if (row.billingMode) return row.billingMode;
  if (row.tieredEnabled && (row.tieredTiers || []).length > 0) return 'tiered';
  if (row.conditionalEnabled && (row.conditionalRules || []).length > 0) {
    return 'conditional';
  }
  if (hasValue(row.fixedPrice)) return 'fixed';
  return 'ratio';
}

function applyBillingMode(row, mode) {
  const next = {
    ...row,
    billingMode: mode,
    tieredEnabled: mode === 'tiered',
    conditionalEnabled: mode === 'conditional',
  };
  if (mode !== 'fixed') next.fixedPrice = '';
  if (mode === 'fixed' && !hasValue(next.fixedPrice)) next.fixedPrice = 0;
  if (mode === 'tiered' && (!next.tieredTiers || next.tieredTiers.length === 0)) {
    next.tieredTiers = [
      {
        min_tokens: 0,
        max_tokens: -1,
        input_price: 0,
        output_price: 0,
        cache_hit_price: 0,
        cache_store_price: 0,
        cache_store_price_5m: 0,
        cache_store_price_1h: 0,
      },
    ];
  }
  if (
    mode === 'conditional' &&
    (!next.conditionalRules || next.conditionalRules.length === 0)
  ) {
    next.conditionalRules = [
      {
        name: '',
        type: 'header',
        key: 'anthropic-beta',
        match: 'contains',
        value: 'fast-mode',
        multiplier: 1.5,
      },
    ];
  }
  return next;
}

function normaliseConfig(config) {
  return config && typeof config === 'object' ? config : {};
}

function clone(value) {
  return JSON.parse(JSON.stringify(value ?? null));
}

function wildcardToRegex(pattern) {
  const escaped = pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^${escaped.replace(/\*/g, '.*')}$`);
}

function wildcardMatches(pattern, target) {
  return pattern.includes('*') && wildcardToRegex(pattern).test(target);
}

function buildRowsFromInputs(inputs) {
  const parsed = {};
  const parseErrors = [];

  [...SIMPLE_JSON_KEYS, 'TieredPricing', 'ConditionalPricing'].forEach((key) => {
    const result = parseJSONWithError(inputs[key], key);
    parsed[key] = result.data;
    if (result.error) parseErrors.push(result.error);
  });

  const names = new Set();
  Object.values(parsed).forEach((config) => {
    Object.keys(normaliseConfig(config)).forEach((name) => names.add(name));
  });

  const rows = Array.from(names)
    .sort((a, b) => a.localeCompare(b))
    .map((name) => {
      const tiered = normaliseConfig(parsed.TieredPricing[name]);
      const conditional = normaliseConfig(parsed.ConditionalPricing[name]);
      const tieredTiers = Array.isArray(tiered.tiers) ? tiered.tiers : [];
      const conditionalRules = Array.isArray(conditional.rules)
        ? conditional.rules
        : [];
      const tieredEnabled =
        tiered.enabled === false ? false : Boolean(tiered.enabled || tieredTiers.length);
      const conditionalEnabled =
        conditional.enabled === false
          ? false
          : Boolean(conditional.enabled || conditionalRules.length);
      const row = {
        key: name,
        name,
        fixedPrice: numberOrBlank(parsed.ModelPrice[name]),
        modelRatio: numberOrBlank(parsed.ModelRatio[name]),
        completionRatio: numberOrBlank(parsed.CompletionRatio[name]),
        cacheRatio: numberOrBlank(parsed.CacheRatio[name]),
        imageRatio: numberOrBlank(parsed.ImageRatio[name]),
        imageCompletionRatio: numberOrBlank(parsed.ImageCompletionRatio[name]),
        audioRatio: numberOrBlank(parsed.AudioRatio[name]),
        audioCompletionRatio: numberOrBlank(parsed.AudioCompletionRatio[name]),
        tieredEnabled,
        tieredTiers,
        conditionalEnabled,
        conditionalStrategy: conditional.strategy || 'first-match',
        conditionalRules,
      };
      return { ...row, billingMode: inferBillingMode(row) };
    });

  return { rows, parseErrors };
}

function buildInputsFromRows(rows, exposeRatioEnabled) {
  const output = {
    ModelPrice: {},
    ModelRatio: {},
    CacheRatio: {},
    TieredPricing: {},
    ConditionalPricing: {},
    CompletionRatio: {},
    ImageRatio: {},
    ImageCompletionRatio: {},
    AudioRatio: {},
    AudioCompletionRatio: {},
    ExposeRatioEnabled: Boolean(exposeRatioEnabled),
  };

  rows.forEach((row) => {
    const name = String(row.name || '').trim();
    if (!name) return;
    const billingMode = inferBillingMode(row);

    if (billingMode === 'fixed' && hasValue(row.fixedPrice)) {
      output.ModelPrice[name] = Number(row.fixedPrice);
    } else {
      if (hasValue(row.modelRatio)) output.ModelRatio[name] = Number(row.modelRatio);
      if (hasValue(row.completionRatio)) {
        output.CompletionRatio[name] = Number(row.completionRatio);
      }
    }

    if (hasValue(row.cacheRatio)) output.CacheRatio[name] = Number(row.cacheRatio);
    if (hasValue(row.imageRatio)) output.ImageRatio[name] = Number(row.imageRatio);
    if (hasValue(row.imageCompletionRatio)) {
      output.ImageCompletionRatio[name] = Number(row.imageCompletionRatio);
    }
    if (hasValue(row.audioRatio)) output.AudioRatio[name] = Number(row.audioRatio);
    if (hasValue(row.audioCompletionRatio)) {
      output.AudioCompletionRatio[name] = Number(row.audioCompletionRatio);
    }

    if (row.tieredEnabled || row.tieredTiers.length > 0) {
      output.TieredPricing[name] = {
        enabled: billingMode === 'tiered' && Boolean(row.tieredEnabled),
        tiers: row.tieredTiers,
      };
    }

    if (row.conditionalEnabled || row.conditionalRules.length > 0) {
      output.ConditionalPricing[name] = {
        enabled: billingMode === 'conditional' && Boolean(row.conditionalEnabled),
        strategy: row.conditionalStrategy || 'first-match',
        rules: row.conditionalRules,
      };
    }
  });

  return Object.fromEntries(
    Object.entries(output).map(([key, value]) => {
      if (typeof value === 'boolean') return [key, value];
      return [key, JSON.stringify(value, null, 2)];
    }),
  );
}

function csvEscape(value) {
  const raw =
    typeof value === 'string' ? value : value === undefined ? '' : String(value);
  return `"${raw.replace(/"/g, '""')}"`;
}

function parseCSV(text) {
  const rows = [];
  let row = [];
  let cell = '';
  let quoted = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];
    if (quoted) {
      if (char === '"' && next === '"') {
        cell += '"';
        i += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        cell += char;
      }
      continue;
    }
    if (char === '"') {
      quoted = true;
    } else if (char === ',') {
      row.push(cell);
      cell = '';
    } else if (char === '\n') {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
    } else if (char !== '\r') {
      cell += char;
    }
  }
  row.push(cell);
  rows.push(row);

  return rows.filter((item) => item.some((value) => value !== ''));
}

function rowsToCSV(rows) {
  const headers = [
    'model',
    'fixed_price',
    'model_ratio',
    'completion_ratio',
    'cache_ratio',
    'image_ratio',
    'image_completion_ratio',
    'audio_ratio',
    'audio_completion_ratio',
    'tiered_enabled',
    'tiered_tiers_json',
    'conditional_enabled',
    'conditional_strategy',
    'conditional_rules_json',
  ];
  const data = rows.map((row) => [
    row.name,
    row.fixedPrice,
    row.modelRatio,
    row.completionRatio,
    row.cacheRatio,
    row.imageRatio,
    row.imageCompletionRatio,
    row.audioRatio,
    row.audioCompletionRatio,
    row.tieredEnabled ? 'true' : 'false',
    JSON.stringify(row.tieredTiers || []),
    row.conditionalEnabled ? 'true' : 'false',
    row.conditionalStrategy || 'first-match',
    JSON.stringify(row.conditionalRules || []),
  ]);
  return [headers, ...data]
    .map((line) => line.map((value) => csvEscape(value)).join(','))
    .join('\n');
}

function csvToRows(text) {
  const parsed = parseCSV(text);
  if (parsed.length < 2) return [];
  const headers = parsed[0].map((value) => value.trim());
  return parsed.slice(1).map((cells) => {
    const item = {};
    headers.forEach((header, index) => {
      item[header] = cells[index] ?? '';
    });
    const row = {
      key: item.model,
      name: item.model,
      fixedPrice: numberOrBlank(item.fixed_price),
      modelRatio: numberOrBlank(item.model_ratio),
      completionRatio: numberOrBlank(item.completion_ratio),
      cacheRatio: numberOrBlank(item.cache_ratio),
      imageRatio: numberOrBlank(item.image_ratio),
      imageCompletionRatio: numberOrBlank(item.image_completion_ratio),
      audioRatio: numberOrBlank(item.audio_ratio),
      audioCompletionRatio: numberOrBlank(item.audio_completion_ratio),
      tieredTiers: safeParseJSON(item.tiered_tiers_json, []),
      conditionalStrategy: item.conditional_strategy || 'first-match',
      conditionalRules: safeParseJSON(item.conditional_rules_json, []),
      tieredEnabled: item.tiered_enabled === 'true',
      conditionalEnabled: item.conditional_enabled === 'true',
    };
    return { ...row, billingMode: inferBillingMode(row) };
  });
}

function getRuleLabel(row) {
  const billingMode = inferBillingMode(row);
  if (billingMode === 'tiered') return '分段计费';
  if (billingMode === 'conditional') return '条件计费';
  if (billingMode === 'fixed') return '按次固定价';
  if (hasValue(row?.modelRatio)) return '按量倍率';
  return '未配置';
}

function getRuleTagColor(rule) {
  switch (rule) {
    case '分段计费':
      return 'cyan';
    case '条件计费':
      return 'violet';
    case '按次固定价':
      return 'green';
    case '按量倍率':
      return 'blue';
    default:
      return 'grey';
  }
}

function formatMaybeNumber(value) {
  if (!hasValue(value)) return '-';
  return Number(value);
}

function formatUsdPerMillion(value) {
  if (!hasValue(value)) return '-';
  return `$${Number(value).toFixed(6).replace(/\.?0+$/, '')}/1M`;
}

function ratioToUsdPerMillion(value) {
  if (!hasValue(value)) return '';
  return Number(value) * 2;
}

function normalisePricingNumber(value) {
  if (!hasValue(value)) return '';
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return '';
  return Number(parsed.toFixed(8));
}

function usdPerMillionToRatio(value) {
  if (!hasValue(value)) return '';
  return normalisePricingNumber(Number(value) / 2);
}

function relativeRatioToUsdPerMillion(baseRatio, relativeRatio, fallback = '') {
  const baseUsd = ratioToUsdPerMillion(baseRatio);
  const resolvedRatio = hasValue(relativeRatio) ? relativeRatio : fallback;
  if (!hasValue(baseUsd) || !hasValue(resolvedRatio)) return '';
  return normalisePricingNumber(Number(baseUsd) * Number(resolvedRatio));
}

function usdPerMillionToRelativeRatio(value, baseRatio) {
  if (!hasValue(value)) return '';
  const baseUsd = ratioToUsdPerMillion(baseRatio);
  if (!hasValue(baseUsd) || Number(baseUsd) === 0) return '';
  return normalisePricingNumber(Number(value) / Number(baseUsd));
}

function getEquivalentUsdPrices(row) {
  const inputUsd = ratioToUsdPerMillion(row?.modelRatio);
  return {
    inputUsd: normalisePricingNumber(inputUsd),
    outputUsd: relativeRatioToUsdPerMillion(row?.modelRatio, row?.completionRatio, 1),
    cacheUsd: relativeRatioToUsdPerMillion(row?.modelRatio, row?.cacheRatio),
    imageInputUsd: relativeRatioToUsdPerMillion(row?.modelRatio, row?.imageRatio),
    imageOutputUsd: relativeRatioToUsdPerMillion(
      row?.modelRatio,
      row?.imageCompletionRatio,
    ),
    audioInputUsd: relativeRatioToUsdPerMillion(row?.modelRatio, row?.audioRatio),
    audioOutputUsd: relativeRatioToUsdPerMillion(
      row?.modelRatio,
      row?.audioCompletionRatio,
    ),
  };
}

function buildEffectiveJsonPreview(nextInputs) {
  return INITIAL_KEYS.reduce((preview, key) => {
    const value = nextInputs[key];
    preview[key] =
      typeof value === 'boolean' ? value : safeParseJSON(value, {});
    return preview;
  }, {});
}

function buildOpenRouterModelCandidates(rawName) {
  const name = String(rawName || '').trim();
  if (!name) return [];
  if (name.includes('*')) return [name];

  const buildNameAliases = (value) => {
    const aliases = [value];
    const dotClaude = value.replace(
      /(claude-(?:opus|sonnet|haiku)-\d+)-(\d+)(?=$|-)/i,
      '$1.$2',
    );
    const hyphenClaude = value.replace(
      /(claude-(?:opus|sonnet|haiku)-\d+)\.(\d+)(?=$|-)/i,
      '$1-$2',
    );
    aliases.push(dotClaude, hyphenClaude);
    return Array.from(new Set(aliases.filter(Boolean)));
  };

  const pushCandidate = (list, value) => {
    buildNameAliases(value).forEach((alias) => {
      list.push(alias);
      list.push(`${alias}*`);
    });
  };

  const candidates = [];
  pushCandidate(candidates, name);
  if (name.includes('/')) {
    const shortName = name.slice(name.lastIndexOf('/') + 1);
    if (shortName) {
      pushCandidate(candidates, shortName);
    }
  } else {
    ['openai', 'anthropic', 'google', 'x-ai', 'meta-llama', 'deepseek'].forEach(
      (provider) => {
        pushCandidate(candidates, `${provider}/${name}`);
      },
    );
  }
  return Array.from(new Set(candidates));
}

function pickExternalSourceValue(sourceData, ratioType, modelCandidates) {
  const sourceMap = normaliseConfig(sourceData?.[ratioType]);
  for (const candidate of modelCandidates) {
    if (!candidate.includes('*') && sourceMap[candidate] !== undefined) {
      return { model: candidate, value: sourceMap[candidate] };
    }
  }
  for (const candidate of modelCandidates) {
    if (!candidate.includes('*')) continue;
    const matched = Object.keys(sourceMap).find((name) =>
      wildcardMatches(candidate, name),
    );
    if (matched) return { model: matched, value: sourceMap[matched] };
  }
  return { model: '', value: undefined };
}

function findModelInMap(modelMap, modelCandidates) {
  const names = Object.keys(modelMap || {});
  for (const candidate of modelCandidates) {
    if (!candidate.includes('*') && modelMap[candidate] !== undefined) {
      return candidate;
    }
  }
  for (const candidate of modelCandidates) {
    if (!candidate.includes('*')) continue;
    const matched = names.find((name) => wildcardMatches(candidate, name));
    if (matched) return matched;
  }
  return names[0] || '';
}

function valuesSame(left, right) {
  if (!hasValue(left) && !hasValue(right)) return true;
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
    return Math.abs(leftNumber - rightNumber) < 0.00000001;
  }
  return left === right;
}

function validateRows(rows, parseErrors, groupRatio) {
  const issues = parseErrors.map((message) => ({
    level: 'error',
    model: 'JSON',
    message,
  }));
  const seen = new Map();
  const groupNames = new Set(Object.keys(groupRatio || {}));

  rows.forEach((row) => {
    const name = String(row.name || '').trim();
    if (!name) {
      issues.push({ level: 'error', model: '-', message: '存在空模型名称' });
      return;
    }

    seen.set(name, (seen.get(name) || 0) + 1);

    const numericFields = [
      ['fixedPrice', '固定价格'],
      ['modelRatio', '模型倍率'],
      ['completionRatio', '补全倍率'],
      ['cacheRatio', '缓存倍率'],
      ['imageRatio', '图片输入倍率'],
      ['imageCompletionRatio', '图片输出倍率'],
      ['audioRatio', '音频输入倍率'],
      ['audioCompletionRatio', '音频输出倍率'],
    ];

    numericFields.forEach(([field, label]) => {
      if (!hasValue(row[field])) return;
      const value = Number(row[field]);
      if (!Number.isFinite(value)) {
        issues.push({
          level: 'error',
          model: name,
          message: `${label} 必须是数字`,
        });
      } else if (value < 0) {
        issues.push({
          level: 'error',
          model: name,
          message: `${label} 不能为负数`,
        });
      }
    });

    if (
      hasValue(row.fixedPrice) &&
      (hasValue(row.modelRatio) || hasValue(row.completionRatio))
    ) {
      issues.push({
        level: 'warning',
        model: name,
        message: '固定价格会覆盖模型倍率和补全倍率，保存时将只保留固定价格',
      });
    }

    if (row.tieredEnabled && row.tieredTiers.length === 0) {
      issues.push({
        level: 'error',
        model: name,
        message: '分段计费已启用，但没有价格区间',
      });
    }

    if (row.conditionalEnabled && row.conditionalRules.length === 0) {
      issues.push({
        level: 'warning',
        model: name,
        message: '条件计费已启用，但没有条件规则',
      });
    }

    const tiers = [...(row.tieredTiers || [])].sort(
      (a, b) => numberValue(a.min_tokens) - numberValue(b.min_tokens),
    );
    tiers.forEach((tier, index) => {
      const min = numberValue(tier.min_tokens);
      const max = numberValue(tier.max_tokens);
      if (min < 0) {
        issues.push({
          level: 'error',
          model: name,
          message: `第 ${index + 1} 个分段 min_tokens 不能为负数`,
        });
      }
      if (max !== -1 && max <= min) {
        issues.push({
          level: 'error',
          model: name,
          message: `第 ${index + 1} 个分段 max_tokens 必须大于 min_tokens，或设为 -1`,
        });
      }
      if (max === -1 && index !== tiers.length - 1) {
        issues.push({
          level: 'error',
          model: name,
          message: 'max_tokens = -1 只能放在最后一个分段',
        });
      }
      [
        'input_price',
        'output_price',
        'cache_hit_price',
        'cache_store_price',
        'cache_store_price_5m',
        'cache_store_price_1h',
      ].forEach((field) => {
        if (tier[field] === undefined) return;
        if (!Number.isFinite(Number(tier[field])) || Number(tier[field]) < 0) {
          issues.push({
            level: 'error',
            model: name,
            message: `第 ${index + 1} 个分段 ${field} 必须是非负数字`,
          });
        }
      });
      const next = tiers[index + 1];
      if (next && max !== numberValue(next.min_tokens)) {
        issues.push({
          level: 'warning',
          model: name,
          message: `第 ${index + 1} 个分段与下一段不连续，请确认是否有断档或重叠`,
        });
      }
    });

    (row.conditionalRules || []).forEach((rule, index) => {
      if (!Number.isFinite(Number(rule.multiplier)) || Number(rule.multiplier) < 0) {
        issues.push({
          level: 'error',
          model: name,
          message: `第 ${index + 1} 条条件计费 multiplier 必须是非负数字`,
        });
      }
      if (rule.group && groupNames.size > 0 && !groupNames.has(rule.group)) {
        issues.push({
          level: 'warning',
          model: name,
          message: `第 ${index + 1} 条条件计费引用了不存在的分组：${rule.group}`,
        });
      }
    });
  });

  seen.forEach((count, name) => {
    if (count > 1) {
      issues.push({
        level: 'error',
        model: name,
        message: '模型名称重复',
      });
    }
  });

  rows.forEach((row) => {
    if (!row.name.includes('*')) return;
    rows.forEach((target) => {
      if (row.name === target.name || target.name.includes('*')) return;
      if (wildcardMatches(row.name, target.name)) {
        issues.push({
          level: 'warning',
          model: target.name,
          message: `同时命中通配符配置 ${row.name}，请确认优先级`,
        });
      }
    });
  });

  return issues;
}

function tierRangeLabel(tier) {
  const max = tier.max_tokens === -1 ? '无上限' : `${tier.max_tokens}K`;
  return `${tier.min_tokens}K - ${max}`;
}

function calculateQuote(row, simulator, groupRatio) {
  if (!row) return null;
  const inputTokens = numberValue(simulator.inputTokens);
  const outputTokens = numberValue(simulator.outputTokens);
  const cacheTokens = numberValue(simulator.cacheTokens);
  const imageInputTokens = numberValue(simulator.imageInputTokens);
  const imageOutputTokens = numberValue(simulator.imageOutputTokens);
  const audioInputTokens = numberValue(simulator.audioInputTokens);
  const audioOutputTokens = numberValue(simulator.audioOutputTokens);
  const group = simulator.group || 'default';
  const groupMultiplier = numberValue(groupRatio?.[group], 1);

  if (row.tieredEnabled && row.tieredTiers.length > 0) {
    const inputK = inputTokens / 1000;
    const tier =
      [...row.tieredTiers]
        .sort((a, b) => numberValue(a.min_tokens) - numberValue(b.min_tokens))
        .find((item) => {
          const min = numberValue(item.min_tokens);
          const max = numberValue(item.max_tokens);
          return inputK >= min && (max === -1 || inputK < max);
        }) || row.tieredTiers[0];
    const inputCost = (inputTokens / 1000000) * numberValue(tier.input_price);
    const outputCost = (outputTokens / 1000000) * numberValue(tier.output_price);
    const cacheCost = (cacheTokens / 1000000) * numberValue(tier.cache_hit_price);
    const total = (inputCost + outputCost + cacheCost) * groupMultiplier;
    return {
      rule: `分段计费 ${tierRangeLabel(tier)}`,
      formula: `(${inputTokens}/1M*${numberValue(tier.input_price)} + ${outputTokens}/1M*${numberValue(tier.output_price)} + ${cacheTokens}/1M*${numberValue(tier.cache_hit_price)}) * 分组 ${groupMultiplier}`,
      total,
    };
  }

  if (hasValue(row.fixedPrice)) {
    const total = numberValue(row.fixedPrice) * groupMultiplier;
    return {
      rule: '按次固定价',
      formula: `${numberValue(row.fixedPrice)} * 分组 ${groupMultiplier}`,
      total,
    };
  }

  const inputPrice = numberValue(row.modelRatio) * 2;
  const outputPrice = inputPrice * numberValue(row.completionRatio, 1);
  const cachePrice = inputPrice * numberValue(row.cacheRatio, 1);
  const imageInputPrice = inputPrice * numberValue(row.imageRatio, 1);
  const imageOutputPrice = inputPrice * numberValue(row.imageCompletionRatio, 1);
  const audioInputPrice = inputPrice * numberValue(row.audioRatio, 1);
  const audioOutputPrice = inputPrice * numberValue(row.audioCompletionRatio, 1);
  const total =
    ((inputTokens / 1000000) * inputPrice +
      (outputTokens / 1000000) * outputPrice +
      (cacheTokens / 1000000) * cachePrice +
      (imageInputTokens / 1000000) * imageInputPrice +
      (imageOutputTokens / 1000000) * imageOutputPrice +
      (audioInputTokens / 1000000) * audioInputPrice +
      (audioOutputTokens / 1000000) * audioOutputPrice) *
    groupMultiplier;

  return {
    rule: hasValue(row.modelRatio) ? '按量倍率' : '未配置倍率',
    formula: `输入价 ${inputPrice}/M，输出价 ${outputPrice}/M，缓存价 ${cachePrice}/M，分组 ${groupMultiplier}`,
    total,
  };
}

export default function ModelRatioSettings(props) {
  const [loading, setLoading] = useState(false);
  const [inputs, setInputs] = useState(INITIAL_INPUTS);
  const [inputsRow, setInputsRow] = useState(INITIAL_INPUTS);
  const [rows, setRows] = useState([]);
  const [parseErrors, setParseErrors] = useState([]);
  const [searchText, setSearchText] = useState('');
  const [ruleFilter, setRuleFilter] = useState('all');
  const [advancedValues, setAdvancedValues] = useState(INITIAL_INPUTS);
  const [editingRow, setEditingRow] = useState(null);
  const [editSourceModel, setEditSourceModel] = useState('');
  const [editSourceQuote, setEditSourceQuote] = useState(null);
  const [editSourceLoading, setEditSourceLoading] = useState(false);
  const [savePreview, setSavePreview] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [simulator, setSimulator] = useState({
    model: '',
    group: 'default',
    inputTokens: 1000,
    outputTokens: 1000,
    cacheTokens: 0,
    imageInputTokens: 0,
    imageOutputTokens: 0,
    audioInputTokens: 0,
    audioOutputTokens: 0,
  });
  const fileInputRef = useRef(null);
  const refForm = useRef();
  const { t } = useTranslation();

  const groupRatio = useMemo(
    () => safeParseJSON(props.options?.GroupRatio, { default: 1 }),
    [props.options],
  );

  const validations = useMemo(
    () => validateRows(rows, parseErrors, groupRatio),
    [rows, parseErrors, groupRatio],
  );

  const hasBlockingError = validations.some((item) => item.level === 'error');

  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      const keywordMatched = searchText
        ? row.name.toLowerCase().includes(searchText.toLowerCase())
        : true;
      const ruleMatched =
        ruleFilter === 'all' || getRuleLabel(row) === ruleFilter;
      return keywordMatched && ruleMatched;
    });
  }, [rows, ruleFilter, searchText]);

  const selectedRow = useMemo(() => {
    return rows.find((row) => row.name === simulator.model) || rows[0] || null;
  }, [rows, simulator.model]);

  const quote = useMemo(
    () => calculateQuote(selectedRow, simulator, groupRatio),
    [groupRatio, selectedRow, simulator],
  );

  useEffect(() => {
    const currentInputs = { ...INITIAL_INPUTS };
    for (let key in props.options) {
      if (INITIAL_KEYS.includes(key)) currentInputs[key] = props.options[key];
    }
    const { rows: nextRows, parseErrors: nextParseErrors } =
      buildRowsFromInputs(currentInputs);
    setInputs(currentInputs);
    setInputsRow(structuredClone(currentInputs));
    setAdvancedValues(currentInputs);
    setRows(nextRows);
    setParseErrors(nextParseErrors);
    if (refForm.current) refForm.current.setValues(currentInputs);
    setSimulator((prev) => ({
      ...prev,
      model:
        prev.model && nextRows.some((row) => row.name === prev.model)
          ? prev.model
          : nextRows[0]?.name || '',
    }));
  }, [props.options]);

  const updateRowsAndInputs = (nextRows, exposeValue = inputs.ExposeRatioEnabled) => {
    setRows(nextRows);
    const nextInputs = buildInputsFromRows(nextRows, exposeValue);
    setInputs(nextInputs);
    setAdvancedValues(nextInputs);
    if (refForm.current) refForm.current.setValues(nextInputs);
    const { parseErrors: nextParseErrors } = buildRowsFromInputs(nextInputs);
    setParseErrors(nextParseErrors);
  };

  const requestSaveConfirmation = (nextInputs, source) => {
    const updateArray = compareObjects(nextInputs, inputsRow);
    if (!updateArray.length) {
      showWarning(t('你似乎还没有修改任何配置'));
      return;
    }

    setSavePreview({
      source,
      nextInputs,
      changedKeys: updateArray.map((item) => item.key),
    });
  };

  const saveInputs = async (nextInputs) => {
    const updateArray = compareObjects(nextInputs, inputsRow);
    if (!updateArray.length) {
      showWarning(t('你似乎还没有修改任何配置'));
      return;
    }

    setLoading(true);
    try {
      const requestQueue = updateArray.map((item) => {
        const value =
          typeof nextInputs[item.key] === 'boolean'
            ? String(nextInputs[item.key])
            : nextInputs[item.key];
        return API.put('/api/option/', { key: item.key, value });
      });

      const res = await Promise.all(requestQueue);
      if (res.includes(undefined)) {
        showError(
          requestQueue.length > 1
            ? t('部分保存失败，请重试')
            : t('保存失败'),
        );
        return;
      }

      for (let i = 0; i < res.length; i += 1) {
        if (!res[i].data.success) {
          showError(res[i].data.message);
          return;
        }
      }

      showSuccess(t('保存成功'));
      setSavePreview(null);
      props.refresh();
    } catch (error) {
      console.error('Unexpected error:', error);
      showError(t('保存失败，请重试'));
    } finally {
      setLoading(false);
    }
  };

  async function onVisualSubmit() {
    if (hasBlockingError) {
      showError(t('存在阻塞级校验错误，请修复后再保存'));
      return;
    }
    const nextInputs = buildInputsFromRows(rows, inputs.ExposeRatioEnabled);
    requestSaveConfirmation(nextInputs, 'workbench');
  }

  async function onAdvancedSubmit() {
    try {
      await refForm.current.validate();
      const { rows: nextRows, parseErrors: nextParseErrors } =
        buildRowsFromInputs(advancedValues);
      const nextIssues = validateRows(nextRows, nextParseErrors, groupRatio);
      if (nextIssues.some((item) => item.level === 'error')) {
        setRows(nextRows);
        setInputs(advancedValues);
        setParseErrors(nextParseErrors);
        showError(t('高级 JSON 存在阻塞级校验错误，请修复后再保存'));
        return;
      }
      setRows(nextRows);
      setInputs(advancedValues);
      setParseErrors(nextParseErrors);
      requestSaveConfirmation(advancedValues, 'advanced');
    } catch (error) {
      console.error(error);
      showError(t('请检查输入'));
    }
  }

  async function resetModelRatio() {
    try {
      let res = await API.post(`/api/option/rest_model_ratio`);
      if (res.data.success) {
        showSuccess(res.data.message);
        props.refresh();
      } else {
        showError(res.data.message);
      }
    } catch (error) {
      showError(error);
    }
  }

  const addModel = () => {
    setEditSourceQuote(null);
    setEditSourceModel('');
    setEditingRow({
      key: '',
      name: '',
      fixedPrice: '',
      modelRatio: '',
      completionRatio: 1,
      cacheRatio: '',
      imageRatio: '',
      imageCompletionRatio: '',
      audioRatio: '',
      audioCompletionRatio: '',
      tieredEnabled: false,
      tieredTiers: [],
      conditionalEnabled: false,
      conditionalStrategy: 'first-match',
      conditionalRules: [],
      billingMode: 'ratio',
      isNew: true,
    });
  };

  const duplicateModel = (row) => {
    const copied = clone(row);
    copied.name = `${row.name}-copy`;
    copied.key = copied.name;
    copied.isNew = true;
    setEditSourceQuote(null);
    setEditSourceModel(copied.name);
    setEditingRow(copied);
  };

  const openEditRow = (row) => {
    setEditSourceQuote(null);
    setEditSourceModel(row.name);
    setEditingRow({ ...clone(row), key: row.name });
  };

  const fetchOpenRouterQuoteForEditing = async () => {
    const modelName = (editSourceModel || editingRow?.name || '').trim();
    if (!modelName) {
      showWarning(t('请先填写 OpenRouter 模型名'));
      return;
    }

    setEditSourceLoading(true);
    setEditSourceQuote(null);
    try {
      const modelCandidates = buildOpenRouterModelCandidates(modelName);
      const res = await API.post('/api/ratio_sync/fetch', {
        source: 'openrouter',
        models: modelCandidates,
        timeout: 20,
      });

      if (!res.data.success) {
        showError(res.data.message || t('获取 OpenRouter 价格失败'));
        return;
      }

      const differences = res.data.data?.differences || {};
      const categories = res.data.data?.categories || {};
      const sourceData = res.data.data?.source_data || {};
      const sourcePicks = {
        model_ratio: pickExternalSourceValue(
          sourceData,
          'model_ratio',
          modelCandidates,
        ),
        completion_ratio: pickExternalSourceValue(
          sourceData,
          'completion_ratio',
          modelCandidates,
        ),
        cache_ratio: pickExternalSourceValue(
          sourceData,
          'cache_ratio',
          modelCandidates,
        ),
      };
      const matchedDiffModel = findModelInMap(differences, modelCandidates);
      const matchedSourceModel =
        sourcePicks.model_ratio.model ||
        sourcePicks.completion_ratio.model ||
        sourcePicks.cache_ratio.model ||
        '';
      const matchedModel = matchedDiffModel || matchedSourceModel;

      if (!matchedModel) {
        setEditSourceQuote({
          model: modelName,
          empty: true,
          message: t('OpenRouter 未返回差异：可能未收录该模型，或当前配置已经一致'),
        });
        setEditSourceQuote((prev) => ({
          ...prev,
          message: t('OpenRouter 未收录或未匹配到该模型'),
        }));
        return;
      }

      const sourceName = 'OpenRouter';
      const diff = differences[matchedModel] || {};
      const pickFromDiff = (key) => {
        const value = diff[key]?.upstreams?.[sourceName];
        return value === 'same' ? diff[key]?.current : value;
      };
      const pick = (key) => {
        const diffValue = pickFromDiff(key);
        if (diffValue !== undefined) return diffValue;
        return sourcePicks[key]?.value;
      };
      const quote = {
        model: matchedModel,
        requestedModel: modelName,
        sourceMatchedModel: matchedSourceModel || matchedModel,
        category: categories[matchedModel] || 'text',
        modelRatio: pick('model_ratio'),
        completionRatio: pick('completion_ratio'),
        cacheRatio: pick('cache_ratio'),
      };
      quote.sameAsCurrent =
        valuesSame(quote.modelRatio, editingRow?.modelRatio) &&
        valuesSame(quote.completionRatio, editingRow?.completionRatio) &&
        valuesSame(quote.cacheRatio, editingRow?.cacheRatio);

      setEditSourceQuote(quote);
      if (
        quote.sameAsCurrent &&
        (quote.modelRatio !== undefined ||
          quote.completionRatio !== undefined ||
          quote.cacheRatio !== undefined)
      ) {
        showSuccess(t('已匹配 OpenRouter，当前配置已与价格源一致'));
        return;
      }
      if (
        quote.modelRatio === undefined &&
        quote.completionRatio === undefined &&
        quote.cacheRatio === undefined
      ) {
        showWarning(t('OpenRouter 没有可回填的按量倍率'));
      } else {
        showSuccess(t('已获取 OpenRouter 参考价格'));
      }
    } catch (error) {
      console.error(error);
      showError(t('请求 OpenRouter 价格失败'));
    } finally {
      setEditSourceLoading(false);
    }
  };

  const applyOpenRouterQuote = () => {
    if (!editSourceQuote || editSourceQuote.empty) return;
    setEditingRow((prev) => ({
      ...prev,
      modelRatio:
        editSourceQuote.modelRatio !== undefined
          ? editSourceQuote.modelRatio
          : prev.modelRatio,
      completionRatio:
        editSourceQuote.completionRatio !== undefined
          ? editSourceQuote.completionRatio
          : prev.completionRatio,
      cacheRatio:
        editSourceQuote.cacheRatio !== undefined
          ? editSourceQuote.cacheRatio
          : prev.cacheRatio,
    }));
    showSuccess(t('已回填 OpenRouter 倍率，请确认后保存'));
  };

  const updateEditingUsdPrice = (field, value) => {
    if (field === 'modelRatio') {
      setEditingRow((prev) => ({
        ...prev,
        modelRatio: usdPerMillionToRatio(value),
      }));
      return;
    }

    if (
      hasValue(value) &&
      (!hasValue(editingRow?.modelRatio) ||
        Number(ratioToUsdPerMillion(editingRow.modelRatio)) === 0)
    ) {
      showWarning(t('请先填写输入价 USD/1M，用它作为其它价格反推倍率的基准'));
      return;
    }

    setEditingRow((prev) => ({
      ...prev,
      [field]: usdPerMillionToRelativeRatio(value, prev.modelRatio),
    }));
  };

  const addTieredRow = () => {
    setEditingRow((prev) => {
      const tiers = prev.tieredTiers || [];
      const last = tiers[tiers.length - 1];
      const nextMin =
        last && Number(last.max_tokens) >= 0 ? Number(last.max_tokens) : 0;
      return {
        ...prev,
        tieredEnabled: true,
        tieredTiers: [
          ...tiers,
          {
            min_tokens: nextMin,
            max_tokens: -1,
            input_price: 0,
            output_price: 0,
            cache_hit_price: 0,
            cache_store_price: 0,
            cache_store_price_5m: 0,
            cache_store_price_1h: 0,
          },
        ],
      };
    });
  };

  const updateTieredRow = (index, field, value) => {
    setEditingRow((prev) => {
      const tiers = [...(prev.tieredTiers || [])];
      tiers[index] = {
        ...tiers[index],
        [field]: value === undefined || value === null ? 0 : Number(value),
      };
      return { ...prev, tieredTiers: tiers };
    });
  };

  const deleteTieredRow = (index) => {
    setEditingRow((prev) => ({
      ...prev,
      tieredTiers: (prev.tieredTiers || []).filter((_, i) => i !== index),
    }));
  };

  const saveEditingRow = () => {
    const next = { ...editingRow, key: editingRow.name };
    if (!next.name || !String(next.name).trim()) {
      showError(t('请输入模型名称'));
      return;
    }
    const rowExists = rows.some((row) => row.name === next.name);
    if (editingRow.isNew && rowExists) {
      showError(t('模型名称已存在'));
      return;
    }
    const nextRows = editingRow.isNew
      ? [next, ...rows]
      : rows.map((row) => (row.name === editingRow.key ? next : row));
    updateRowsAndInputs(nextRows);
    setEditingRow(null);
    setEditSourceQuote(null);
    setEditSourceModel('');
  };

  const deleteModel = (row) => {
    const nextRows = rows.filter((item) => item.name !== row.name);
    updateRowsAndInputs(nextRows);
  };

  const exportCSV = () => {
    const blob = new Blob([rowsToCSV(rows)], {
      type: 'text/csv;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `model-pricing-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const importCSV = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    try {
      const text = await file.text();
      const importedRows = csvToRows(text);
      if (!importedRows.length) {
        showError(t('CSV 中没有可导入的数据'));
        return;
      }
      const merged = new Map(rows.map((row) => [row.name, row]));
      importedRows.forEach((row) => {
        if (row.name) merged.set(row.name, row);
      });
      const nextRows = Array.from(merged.values());
      updateRowsAndInputs(nextRows);
      showSuccess(
        t('导入完成：新增或更新 {{count}} 个模型', {
          count: importedRows.length,
        }),
      );
    } catch (error) {
      console.error(error);
      showError(t('CSV 导入失败，请检查文件格式'));
    }
  };

  const columns = [
    {
      title: t('模型名称'),
      dataIndex: 'name',
      width: 240,
      render: (text) => (
        <Space>
          <Text strong>{text}</Text>
          {String(text).includes('*') && (
            <Tag color='blue' size='small'>
              {t('通配符')}
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: t('当前生效规则'),
      width: 140,
      render: (_, row) => {
        const rule = getRuleLabel(row);
        return <Tag color={getRuleTagColor(rule)}>{t(rule)}</Tag>;
      },
    },
    {
      title: t('按次价'),
      dataIndex: 'fixedPrice',
      width: 100,
      render: (value) => (hasValue(value) ? `$${formatMaybeNumber(value)}` : '-'),
    },
    {
      title: t('输入/输出倍率'),
      width: 140,
      render: (_, row) =>
        hasValue(row.modelRatio)
          ? `${formatMaybeNumber(row.modelRatio)} / ${formatMaybeNumber(
              row.completionRatio || 1,
            )}`
          : '-',
    },
    {
      title: t('等价美元价'),
      width: 220,
      render: (_, row) => {
        const prices = getEquivalentUsdPrices(row);
        if (!hasValue(prices.inputUsd)) return '-';
        return (
          <Space wrap>
            <Tag size='small'>{t('输入')} {formatUsdPerMillion(prices.inputUsd)}</Tag>
            <Tag size='small'>{t('输出')} {formatUsdPerMillion(prices.outputUsd)}</Tag>
            {hasValue(prices.cacheUsd) && (
              <Tag size='small'>C {formatUsdPerMillion(prices.cacheUsd)}</Tag>
            )}
          </Space>
        );
      },
    },
    {
      title: t('缓存/图片/音频'),
      width: 180,
      render: (_, row) => (
        <Space wrap>
          {hasValue(row.cacheRatio) && <Tag size='small'>C {row.cacheRatio}</Tag>}
          {hasValue(row.imageRatio) && <Tag size='small'>I {row.imageRatio}</Tag>}
          {hasValue(row.imageCompletionRatio) && (
            <Tag size='small'>IO {row.imageCompletionRatio}</Tag>
          )}
          {hasValue(row.audioRatio) && <Tag size='small'>A {row.audioRatio}</Tag>}
          {hasValue(row.audioCompletionRatio) && (
            <Tag size='small'>AO {row.audioCompletionRatio}</Tag>
          )}
          {!hasValue(row.cacheRatio) &&
            !hasValue(row.imageRatio) &&
            !hasValue(row.imageCompletionRatio) &&
            !hasValue(row.audioRatio) &&
            !hasValue(row.audioCompletionRatio) &&
            '-'}
        </Space>
      ),
    },
    {
      title: t('分段/条件'),
      width: 160,
      render: (_, row) => (
        <Space wrap>
          <Tag color={row.tieredEnabled ? 'cyan' : 'grey'} size='small'>
            {t('分段')} {row.tieredTiers.length}
          </Tag>
          <Tag color={row.conditionalEnabled ? 'violet' : 'grey'} size='small'>
            {t('条件')} {row.conditionalRules.length}
          </Tag>
        </Space>
      ),
    },
    {
      title: t('校验'),
      width: 180,
      render: (_, row) => {
        const rowIssues = validations.filter((item) => item.model === row.name);
        if (!rowIssues.length) return <Tag color='green'>{t('正常')}</Tag>;
        const hasError = rowIssues.some((item) => item.level === 'error');
        return (
          <Tag color={hasError ? 'red' : 'orange'}>
            {hasError ? t('需修复') : t('需确认')} {rowIssues.length}
          </Tag>
        );
      },
    },
    {
      title: t('操作'),
      width: 160,
      fixed: 'right',
      render: (_, row) => (
        <Space>
          <Button
            icon={<IconEdit />}
            size='small'
            onClick={() => openEditRow(row)}
          />
          <Button
            icon={<IconCopy />}
            size='small'
            onClick={() => duplicateModel(row)}
          />
          <Popconfirm
            title={t('确定删除该模型价格配置吗？')}
            onConfirm={() => deleteModel(row)}
          >
            <Button icon={<IconDelete />} type='danger' size='small' />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const renderValidationPanel = () => {
    if (!validations.length) {
      return (
        <Banner
          type='success'
          fullMode={false}
          description={t('价格配置校验通过，可以保存或导出。')}
        />
      );
    }

    const errors = validations.filter((item) => item.level === 'error');
    const warnings = validations.filter((item) => item.level !== 'error');
    return (
      <Banner
        type={errors.length ? 'danger' : 'warning'}
        icon={<IconAlertTriangle />}
        fullMode={false}
        description={
          <div>
            <Text strong>
              {errors.length
                ? t('存在 {{count}} 个阻塞错误', { count: errors.length })
                : t('存在 {{count}} 个需要确认的提醒', {
                    count: warnings.length,
                  })}
            </Text>
            <div style={{ marginTop: 8, maxHeight: 120, overflow: 'auto' }}>
              {validations.slice(0, 8).map((issue, index) => (
                <div key={`${issue.model}-${index}`}>
                  <Tag
                    color={issue.level === 'error' ? 'red' : 'orange'}
                    size='small'
                    style={{ marginRight: 6 }}
                  >
                    {issue.level === 'error' ? t('错误') : t('提醒')}
                  </Tag>
                  <Text>
                    {issue.model}: {issue.message}
                  </Text>
                </div>
              ))}
            </div>
          </div>
        }
      />
    );
  };

  const renderSimulator = () => {
    const groupOptions = Object.keys(groupRatio || { default: 1 }).map((group) => ({
      label: `${group} (${groupRatio[group]})`,
      value: group,
    }));
    const modelOptions = rows.map((row) => ({ label: row.name, value: row.name }));

    return (
      <div style={{ borderTop: '1px solid var(--semi-color-border)', paddingTop: 16 }}>
        <Title heading={6}>{t('价格试算器')}</Title>
        <Row gutter={[12, 12]}>
          <Col xs={24} md={8}>
            <Select
              prefix={t('模型')}
              value={selectedRow?.name || ''}
              optionList={modelOptions}
              filter
              showClear={false}
              style={{ width: '100%' }}
              onChange={(value) =>
                setSimulator((prev) => ({ ...prev, model: value }))
              }
            />
          </Col>
          <Col xs={24} md={8}>
            <Select
              prefix={t('分组')}
              value={simulator.group}
              optionList={groupOptions}
              style={{ width: '100%' }}
              onChange={(value) =>
                setSimulator((prev) => ({ ...prev, group: value }))
              }
            />
          </Col>
          <Col xs={12} md={4}>
            <InputNumber
              prefix={t('输入')}
              suffix='tokens'
              min={0}
              value={simulator.inputTokens}
              onChange={(value) =>
                setSimulator((prev) => ({ ...prev, inputTokens: value }))
              }
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={12} md={4}>
            <InputNumber
              prefix={t('输出')}
              suffix='tokens'
              min={0}
              value={simulator.outputTokens}
              onChange={(value) =>
                setSimulator((prev) => ({ ...prev, outputTokens: value }))
              }
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={12} md={4}>
            <InputNumber
              prefix={t('缓存')}
              suffix='tokens'
              min={0}
              value={simulator.cacheTokens}
              onChange={(value) =>
                setSimulator((prev) => ({ ...prev, cacheTokens: value }))
              }
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={12} md={5}>
            <InputNumber
              prefix={t('图片输入')}
              suffix='tokens'
              min={0}
              value={simulator.imageInputTokens}
              onChange={(value) =>
                setSimulator((prev) => ({ ...prev, imageInputTokens: value }))
              }
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={12} md={5}>
            <InputNumber
              prefix={t('图片输出')}
              suffix='tokens'
              min={0}
              value={simulator.imageOutputTokens}
              onChange={(value) =>
                setSimulator((prev) => ({ ...prev, imageOutputTokens: value }))
              }
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={12} md={5}>
            <InputNumber
              prefix={t('音频输入')}
              suffix='tokens'
              min={0}
              value={simulator.audioInputTokens}
              onChange={(value) =>
                setSimulator((prev) => ({ ...prev, audioInputTokens: value }))
              }
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={12} md={5}>
            <InputNumber
              prefix={t('音频输出')}
              suffix='tokens'
              min={0}
              value={simulator.audioOutputTokens}
              onChange={(value) =>
                setSimulator((prev) => ({ ...prev, audioOutputTokens: value }))
              }
              style={{ width: '100%' }}
            />
          </Col>
        </Row>
        <div
          style={{
            marginTop: 12,
            padding: 12,
            border: '1px solid var(--semi-color-border)',
            borderRadius: 6,
            background: 'var(--semi-color-fill-0)',
          }}
        >
          {quote ? (
            <Space vertical align='start'>
              <Text>
                {t('命中规则')}：<Tag color={getRuleTagColor(quote.rule)}>{quote.rule}</Tag>
              </Text>
              <Text>{t('计算公式')}：{quote.formula}</Text>
              <Text strong>{t('预计扣费')}：${quote.total.toFixed(8)}</Text>
            </Space>
          ) : (
            <Text type='tertiary'>{t('请选择模型后开始试算')}</Text>
          )}
        </div>
      </div>
    );
  };

  const renderVisualWorkbench = () => (
    <Space vertical align='start' style={{ width: '100%' }} spacing='medium'>
      {renderValidationPanel()}
      <Space wrap>
        <Button icon={<IconPlus />} onClick={addModel}>
          {t('添加模型')}
        </Button>
        <Button
          type='primary'
          icon={<IconSave />}
          loading={loading}
          disabled={hasBlockingError}
          onClick={onVisualSubmit}
        >
          {t('保存价格配置')}
        </Button>
        <Button icon={<IconDownload />} onClick={exportCSV}>
          {t('导出 CSV')}
        </Button>
        <Button icon={<IconUpload />} onClick={() => fileInputRef.current?.click()}>
          {t('导入 CSV')}
        </Button>
        <input
          ref={fileInputRef}
          type='file'
          accept='.csv,text/csv'
          style={{ display: 'none' }}
          onChange={importCSV}
        />
        <Input
          prefix={<IconSearch />}
          placeholder={t('搜索模型名称')}
          value={searchText}
          onChange={(value) => {
            setSearchText(value);
            setCurrentPage(1);
          }}
          showClear
          style={{ width: 220 }}
        />
        <Select
          value={ruleFilter}
          style={{ width: 160 }}
          optionList={[
            { label: t('全部规则'), value: 'all' },
            { label: t('分段计费'), value: '分段计费' },
            { label: t('条件计费'), value: '条件计费' },
            { label: t('按次固定价'), value: '按次固定价' },
            { label: t('按量倍率'), value: '按量倍率' },
            { label: t('未配置'), value: '未配置' },
          ]}
          onChange={(value) => {
            setRuleFilter(value);
            setCurrentPage(1);
          }}
        />
        <Switch
          checked={Boolean(inputs.ExposeRatioEnabled)}
          checkedText={t('倍率接口开')}
          uncheckedText={t('倍率接口关')}
          onChange={(value) => {
            setInputs((prev) => ({ ...prev, ExposeRatioEnabled: value }));
            updateRowsAndInputs(rows, value);
          }}
        />
      </Space>
      <Table
        columns={columns}
        dataSource={filteredRows}
        rowKey='name'
        scroll={{ x: 1180 }}
        pagination={{
          currentPage,
          pageSize: 10,
          total: filteredRows.length,
          showTotal: true,
          onPageChange: setCurrentPage,
        }}
      />
      {renderSimulator()}
    </Space>
  );

  const renderAdvancedEditor = () => (
    <Form
      values={advancedValues}
      getFormApi={(formAPI) => (refForm.current = formAPI)}
      style={{ marginBottom: 15 }}
    >
      <Banner
        type='info'
        fullMode={false}
        description={t(
          '高级模式直接编辑后端保存的 JSON。普通运营建议优先使用上方工作台；这里适合批量粘贴、审计和紧急修复。',
        )}
        style={{ marginBottom: 16 }}
      />
      {JSON_FIELD_META.map((field) => (
        <Row gutter={16} key={field.key}>
          <Col xs={24} sm={18}>
            <Form.TextArea
              label={t(field.label)}
              extraText={t(field.help)}
              placeholder={field.placeholder}
              field={field.key}
              autosize={{ minRows: 5, maxRows: 12 }}
              trigger='blur'
              stopValidateWithError
              rules={[
                {
                  validator: (rule, value) => verifyJSON(value),
                  message: t('不是合法的 JSON 字符串'),
                },
              ]}
              onChange={(value) =>
                setAdvancedValues((prev) => ({ ...prev, [field.key]: value }))
              }
            />
          </Col>
        </Row>
      ))}
      <Row gutter={16}>
        <Col span={18}>
          <Form.Switch
            label={t('暴露倍率接口')}
            field='ExposeRatioEnabled'
            onChange={(value) =>
              setAdvancedValues((prev) => ({
                ...prev,
                ExposeRatioEnabled: value,
              }))
            }
          />
        </Col>
      </Row>
      <Space>
        <Button
          type='primary'
          icon={<IconSave />}
          loading={loading}
          onClick={onAdvancedSubmit}
        >
          {t('保存高级 JSON')}
        </Button>
        <Button
          icon={<IconRefresh />}
          onClick={() => {
            const { rows: nextRows, parseErrors: nextParseErrors } =
              buildRowsFromInputs(advancedValues);
            setRows(nextRows);
            setInputs(advancedValues);
            setParseErrors(nextParseErrors);
            showSuccess(t('已从高级 JSON 重新生成工作台数据'));
          }}
        >
          {t('同步到工作台')}
        </Button>
      </Space>
    </Form>
  );

  const formatConditionRule = (rule) => {
    if (!rule) return '-';
    if (rule.type === 'time') {
      const hours =
        rule.start_hour === rule.end_hour
          ? t('全天')
          : `${numberValue(rule.start_hour)}:00-${numberValue(rule.end_hour)}:00`;
      const weekdays =
        Array.isArray(rule.weekdays) && rule.weekdays.length
          ? ` ${t('周')} ${rule.weekdays.join(',')}`
          : '';
      return `${rule.timezone || 'UTC'} ${hours}${weekdays}`;
    }
    const source = rule.type === 'param' ? 'param' : 'header';
    const match = rule.match || 'contains';
    return `${source} ${rule.key || '-'} ${match}${
      match === 'exists' ? '' : ` "${rule.value || ''}"`
    }`;
  };

  const renderEffectivePricePanel = (row) => {
    if (!row) return null;
    const billingMode = inferBillingMode(row);
    const prices = getEquivalentUsdPrices(row);

    if (billingMode === 'tiered') {
      return (
        <div style={{ marginTop: 12 }}>
          <Text strong>{t('真实生效价格')}</Text>
          <Table
            size='small'
            pagination={false}
            rowKey='index'
            style={{ marginTop: 8 }}
            dataSource={(row.tieredTiers || []).map((tier, index) => ({
              ...tier,
              index,
            }))}
            columns={[
              {
                title: t('输入区间'),
                width: 150,
                render: (_, tier) =>
                  `${tier.min_tokens ?? 0} - ${
                    Number(tier.max_tokens) === -1 ? '∞' : tier.max_tokens
                  }`,
              },
              {
                title: t('输入'),
                render: (_, tier) => formatUsdPerMillion(tier.input_price),
              },
              {
                title: t('输出'),
                render: (_, tier) => formatUsdPerMillion(tier.output_price),
              },
              {
                title: t('缓存命中'),
                render: (_, tier) => formatUsdPerMillion(tier.cache_hit_price),
              },
              {
                title: t('缓存写入'),
                render: (_, tier) => (
                  <Space wrap>
                    <Tag size='small'>base {formatUsdPerMillion(tier.cache_store_price)}</Tag>
                    <Tag size='small'>5m {formatUsdPerMillion(tier.cache_store_price_5m)}</Tag>
                    <Tag size='small'>1h {formatUsdPerMillion(tier.cache_store_price_1h)}</Tag>
                  </Space>
                ),
              },
            ]}
          />
        </div>
      );
    }

    if (billingMode === 'fixed') {
      return (
        <div style={{ marginTop: 12 }}>
          <Text strong>{t('真实生效价格')}</Text>
          <div style={{ marginTop: 8 }}>
            <Tag color='green' size='large'>
              {t('每次请求')} ${formatMaybeNumber(row.fixedPrice)}
            </Tag>
          </div>
        </div>
      );
    }

    return (
      <div style={{ marginTop: 12 }}>
        <Text strong>{t('真实生效价格')}</Text>
        <div style={{ marginTop: 8 }}>
          <Space wrap>
            <Tag color='blue'>{t('输入')} {formatUsdPerMillion(prices.inputUsd)}</Tag>
            <Tag color='blue'>{t('输出')} {formatUsdPerMillion(prices.outputUsd)}</Tag>
            {hasValue(prices.cacheUsd) && (
              <Tag color='cyan'>{t('缓存命中')} {formatUsdPerMillion(prices.cacheUsd)}</Tag>
            )}
            {billingMode === 'conditional' && (
              <Tag color='violet'>
                {t('条件命中后乘数叠加')} {row.conditionalStrategy || 'first-match'}
              </Tag>
            )}
          </Space>
        </div>
      </div>
    );
  };

  const renderTextRatioFields = () => (
    <>
      {renderEquivalentUsdEditor()}
      <Text type='secondary'>
        {t('倍率原始值：上方美元价会同步改写这里；也可以直接编辑倍率。')}
      </Text>
      <div style={{ height: 8 }} />
      <Row gutter={12}>
        <Col span={8}>
          {renderNumberField({
            label: t('模型倍率'),
            value: editingRow.modelRatio,
            onChange: (value) =>
              setEditingRow((prev) => ({ ...prev, modelRatio: value })),
          })}
        </Col>
        <Col span={8}>
          {renderNumberField({
            label: t('补全倍率'),
            value: editingRow.completionRatio,
            onChange: (value) =>
              setEditingRow((prev) => ({ ...prev, completionRatio: value })),
          })}
        </Col>
        <Col span={8}>
          {renderNumberField({
            label: t('缓存倍率'),
            value: editingRow.cacheRatio,
            onChange: (value) =>
              setEditingRow((prev) => ({ ...prev, cacheRatio: value })),
          })}
        </Col>
      </Row>
      <Divider margin='12px'>{t('多模态倍率：图片、音频')}</Divider>
      <Row gutter={12}>
        <Col span={8}>
          {renderNumberField({
            label: t('图片输入倍率'),
            value: editingRow.imageRatio,
            onChange: (value) =>
              setEditingRow((prev) => ({ ...prev, imageRatio: value })),
          })}
        </Col>
        <Col span={8}>
          {renderNumberField({
            label: t('图片输出倍率'),
            value: editingRow.imageCompletionRatio,
            onChange: (value) =>
              setEditingRow((prev) => ({
                ...prev,
                imageCompletionRatio: value,
              })),
          })}
        </Col>
        <Col span={8}>
          {renderNumberField({
            label: t('音频输入倍率'),
            value: editingRow.audioRatio,
            onChange: (value) =>
              setEditingRow((prev) => ({ ...prev, audioRatio: value })),
          })}
        </Col>
      </Row>
      <Row gutter={12}>
        <Col span={8}>
          {renderNumberField({
            label: t('音频输出倍率'),
            value: editingRow.audioCompletionRatio,
            onChange: (value) =>
              setEditingRow((prev) => ({
                ...prev,
                audioCompletionRatio: value,
              })),
          })}
        </Col>
      </Row>
    </>
  );

  const renderFixedPriceFields = () => (
    <Row gutter={12}>
      <Col span={8}>
        {renderNumberField({
          label: t('固定价格'),
          value: editingRow.fixedPrice,
          suffix: 'USD/次',
          onChange: (value) =>
            setEditingRow((prev) => ({ ...prev, fixedPrice: value })),
        })}
      </Col>
    </Row>
  );

  const renderTieredPricingFields = () => (
    <div>
      <Row style={{ marginBottom: 10 }} type='flex' align='middle'>
        <Col span={16}>
          <Text type='secondary'>
            {t('按输入 token 区间命中价格；max_tokens = -1 表示无上限。')}
          </Text>
        </Col>
        <Col span={8} style={{ textAlign: 'right' }}>
          <Button icon={<IconPlus />} onClick={addTieredRow}>
            {t('添加分段')}
          </Button>
        </Col>
      </Row>
      <Table
        size='small'
        pagination={false}
        rowKey='index'
        scroll={{ x: 1320 }}
        dataSource={(editingRow.tieredTiers || []).map((tier, index) => ({
          ...tier,
          index,
        }))}
        empty={t('暂无分段，点击“添加分段”创建第一段')}
        columns={[
          {
            title: t('最小 tokens'),
            dataIndex: 'min_tokens',
            width: 130,
            render: (value, record) => (
              <InputNumber
                value={value}
                min={0}
                precision={0}
                style={{ width: '100%' }}
                onChange={(nextValue) =>
                  updateTieredRow(record.index, 'min_tokens', nextValue)
                }
              />
            ),
          },
          {
            title: t('最大 tokens'),
            dataIndex: 'max_tokens',
            width: 130,
            render: (value, record) => (
              <InputNumber
                value={value}
                min={-1}
                precision={0}
                style={{ width: '100%' }}
                onChange={(nextValue) =>
                  updateTieredRow(record.index, 'max_tokens', nextValue)
                }
              />
            ),
          },
          {
            title: t('输入 USD/1M'),
            dataIndex: 'input_price',
            width: 150,
            render: (value, record) => (
              <InputNumber
                value={value}
                min={0}
                precision={8}
                style={{ width: '100%' }}
                onChange={(nextValue) =>
                  updateTieredRow(record.index, 'input_price', nextValue)
                }
              />
            ),
          },
          {
            title: t('输出 USD/1M'),
            dataIndex: 'output_price',
            width: 150,
            render: (value, record) => (
              <InputNumber
                value={value}
                min={0}
                precision={8}
                style={{ width: '100%' }}
                onChange={(nextValue) =>
                  updateTieredRow(record.index, 'output_price', nextValue)
                }
              />
            ),
          },
          {
            title: t('缓存命中 USD/1M'),
            dataIndex: 'cache_hit_price',
            width: 150,
            render: (value, record) => (
              <InputNumber
                value={value}
                min={0}
                precision={8}
                style={{ width: '100%' }}
                onChange={(nextValue) =>
                  updateTieredRow(record.index, 'cache_hit_price', nextValue)
                }
              />
            ),
          },
          {
            title: t('缓存写入 USD/1M'),
            dataIndex: 'cache_store_price',
            width: 150,
            render: (value, record) => (
              <InputNumber
                value={value}
                min={0}
                precision={8}
                style={{ width: '100%' }}
                onChange={(nextValue) =>
                  updateTieredRow(record.index, 'cache_store_price', nextValue)
                }
              />
            ),
          },
          {
            title: t('写入 5m USD/1M'),
            dataIndex: 'cache_store_price_5m',
            width: 150,
            render: (value, record) => (
              <InputNumber
                value={value}
                min={0}
                precision={8}
                style={{ width: '100%' }}
                onChange={(nextValue) =>
                  updateTieredRow(record.index, 'cache_store_price_5m', nextValue)
                }
              />
            ),
          },
          {
            title: t('写入 1h USD/1M'),
            dataIndex: 'cache_store_price_1h',
            width: 150,
            render: (value, record) => (
              <InputNumber
                value={value}
                min={0}
                precision={8}
                style={{ width: '100%' }}
                onChange={(nextValue) =>
                  updateTieredRow(record.index, 'cache_store_price_1h', nextValue)
                }
              />
            ),
          },
          {
            title: t('操作'),
            width: 80,
            render: (_, record) => (
              <Button
                type='danger'
                size='small'
                icon={<IconDelete />}
                onClick={() => deleteTieredRow(record.index)}
              />
            ),
          },
        ]}
      />
    </div>
  );

  const addConditionalRule = () => {
    setEditingRow((prev) => ({
      ...prev,
      conditionalRules: [
        ...(prev.conditionalRules || []),
        {
          name: '',
          type: 'header',
          key: 'anthropic-beta',
          match: 'contains',
          value: 'fast-mode',
          multiplier: 1.5,
        },
      ],
    }));
  };

  const updateConditionalRule = (index, patch) => {
    setEditingRow((prev) => {
      const rules = [...(prev.conditionalRules || [])];
      rules[index] = { ...rules[index], ...patch };
      return { ...prev, conditionalRules: rules };
    });
  };

  const deleteConditionalRule = (index) => {
    setEditingRow((prev) => ({
      ...prev,
      conditionalRules: (prev.conditionalRules || []).filter((_, i) => i !== index),
    }));
  };

  const renderConditionalPricingFields = () => (
    <div>
      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col span={10}>
          <Text type='secondary'>{t('命中策略')}</Text>
          <Select
            value={editingRow.conditionalStrategy || 'first-match'}
            optionList={CONDITION_STRATEGY_OPTIONS}
            style={{ width: '100%', marginTop: 6 }}
            onChange={(value) =>
              setEditingRow((prev) => ({
                ...prev,
                conditionalStrategy: value,
              }))
            }
          />
        </Col>
        <Col span={14} style={{ textAlign: 'right', paddingTop: 24 }}>
          <Button icon={<IconPlus />} onClick={addConditionalRule}>
            {t('添加条件规则')}
          </Button>
        </Col>
      </Row>
      <Table
        size='small'
        pagination={false}
        rowKey='index'
        scroll={{ x: 1180 }}
        dataSource={(editingRow.conditionalRules || []).map((rule, index) => ({
          ...rule,
          index,
        }))}
        empty={t('暂无条件规则')}
        columns={[
          {
            title: t('规则名'),
            width: 150,
            render: (_, record) => (
              <Input
                value={record.name}
                placeholder='fast-mode'
                onChange={(value) =>
                  updateConditionalRule(record.index, { name: value })
                }
              />
            ),
          },
          {
            title: t('类型'),
            width: 150,
            render: (_, record) => (
              <Select
                value={record.type || 'header'}
                optionList={CONDITION_TYPE_OPTIONS}
                style={{ width: '100%' }}
                onChange={(value) =>
                  updateConditionalRule(record.index, {
                    type: value,
                    key: value === 'time' ? '' : record.key || 'anthropic-beta',
                    match: value === 'time' ? '' : record.match || 'contains',
                  })
                }
              />
            ),
          },
          {
            title: t('条件'),
            width: 470,
            render: (_, record) =>
              record.type === 'time' ? (
                <Space>
                  <Input
                    value={record.timezone || 'UTC'}
                    placeholder='Asia/Shanghai'
                    style={{ width: 150 }}
                    onChange={(value) =>
                      updateConditionalRule(record.index, { timezone: value })
                    }
                  />
                  <InputNumber
                    value={record.start_hour || 0}
                    min={0}
                    max={24}
                    precision={0}
                    style={{ width: 88 }}
                    onChange={(value) =>
                      updateConditionalRule(record.index, { start_hour: value })
                    }
                  />
                  <InputNumber
                    value={record.end_hour || 0}
                    min={0}
                    max={24}
                    precision={0}
                    style={{ width: 88 }}
                    onChange={(value) =>
                      updateConditionalRule(record.index, { end_hour: value })
                    }
                  />
                  <Select
                    multiple
                    value={record.weekdays || []}
                    optionList={WEEKDAY_OPTIONS}
                    placeholder={t('不限星期')}
                    style={{ width: 130 }}
                    onChange={(value) =>
                      updateConditionalRule(record.index, { weekdays: value })
                    }
                  />
                </Space>
              ) : (
                <Space>
                  <Input
                    value={record.key || ''}
                    placeholder={record.type === 'param' ? 'service_tier' : 'anthropic-beta'}
                    style={{ width: 150 }}
                    onChange={(value) =>
                      updateConditionalRule(record.index, { key: value })
                    }
                  />
                  <Select
                    value={record.match || 'contains'}
                    optionList={CONDITION_MATCH_OPTIONS}
                    style={{ width: 140 }}
                    onChange={(value) =>
                      updateConditionalRule(record.index, { match: value })
                    }
                  />
                  {(record.match || 'contains') !== 'exists' && (
                    <Input
                      value={record.value || ''}
                      placeholder='fast-mode / priority'
                      style={{ width: 150 }}
                      onChange={(value) =>
                        updateConditionalRule(record.index, { value })
                      }
                    />
                  )}
                </Space>
              ),
          },
          {
            title: t('乘数'),
            width: 120,
            render: (_, record) => (
              <InputNumber
                value={record.multiplier}
                min={0}
                precision={4}
                style={{ width: '100%' }}
                onChange={(value) =>
                  updateConditionalRule(record.index, { multiplier: value })
                }
              />
            ),
          },
          {
            title: t('预览'),
            width: 220,
            render: (_, record) => (
              <Text type='secondary'>
                {formatConditionRule(record)} ×{formatMaybeNumber(record.multiplier)}
              </Text>
            ),
          },
          {
            title: t('操作'),
            width: 80,
            render: (_, record) => (
              <Button
                type='danger'
                size='small'
                icon={<IconDelete />}
                onClick={() => deleteConditionalRule(record.index)}
              />
            ),
          },
        ]}
      />
    </div>
  );

  const renderBillingModeEditor = () => {
    if (!editingRow) return null;
    const billingMode = inferBillingMode(editingRow);
    return (
      <div style={{ marginTop: 12 }}>
        <Divider margin='12px'>{t('计费方式')}</Divider>
        <Row gutter={12} style={{ marginBottom: 12 }}>
          <Col span={10}>
            <Text type='secondary'>{t('当前编辑的计费方式')}</Text>
            <Select
              value={billingMode}
              optionList={BILLING_MODE_OPTIONS}
              style={{ width: '100%', marginTop: 6 }}
              onChange={(value) =>
                setEditingRow((prev) => applyBillingMode(prev, value))
              }
            />
          </Col>
          <Col span={14}>
            <Banner
              type={billingMode === 'tiered' || billingMode === 'conditional' ? 'warning' : 'info'}
              fullMode={false}
              description={
                billingMode === 'tiered'
                  ? t('分段计费会优先按输入 token 区间生效。')
                  : billingMode === 'conditional'
                    ? t('条件计费会在基础价格之上叠加命中乘数。')
                    : billingMode === 'fixed'
                      ? t('按次固定价会覆盖 token 倍率。')
                      : t('按量 Token 计费使用输入/输出/缓存倍率。')
              }
            />
          </Col>
        </Row>
        {billingMode === 'fixed' && renderFixedPriceFields()}
        {billingMode === 'ratio' && renderTextRatioFields()}
        {billingMode === 'tiered' && renderTieredPricingFields()}
        {billingMode === 'conditional' && renderConditionalPricingFields()}
      </div>
    );
  };

  const renderEditSummaryPanel = () => {
    if (!editingRow) return null;
    const draftIssues = validateRows(
      [{ ...editingRow, key: editingRow.name || editingRow.key || '' }],
      [],
      groupRatio,
    ).filter((item) => item.model === (editingRow.name || '-'));
    const rule = getRuleLabel(editingRow);
    const prices = getEquivalentUsdPrices(editingRow);

    return (
      <div
        style={{
          border: '1px solid var(--semi-color-border)',
          borderRadius: 8,
          padding: 14,
          marginBottom: 14,
          background: 'var(--semi-color-bg-0)',
        }}
      >
        <Row gutter={16}>
          <Col span={8}>
            <Text type='secondary'>{t('当前生效规则')}</Text>
            <div style={{ marginTop: 8 }}>
              <Tag color={getRuleTagColor(rule)} size='large'>
                {t(rule)}
              </Tag>
            </div>
          </Col>
          <Col span={8}>
            <Text type='secondary'>{t('基准 Token 价')}</Text>
            <div style={{ marginTop: 8 }}>
              <Text strong>
                {t('输入')} {formatUsdPerMillion(prices.inputUsd)}
              </Text>
              <br />
              <Text strong>
                {t('输出')} {formatUsdPerMillion(prices.outputUsd)}
              </Text>
              {(rule === '分段计费' || rule === '条件计费') && (
                <>
                  <br />
                  <Text type='tertiary'>{t('最终以真实生效价格为准')}</Text>
                </>
              )}
            </div>
          </Col>
          <Col span={8}>
            <Text type='secondary'>{t('草稿校验')}</Text>
            <div style={{ marginTop: 8 }}>
              {draftIssues.length === 0 ? (
                <Tag color='green'>{t('正常')}</Tag>
              ) : (
                <Tag
                  color={
                    draftIssues.some((item) => item.level === 'error')
                      ? 'red'
                      : 'orange'
                  }
                >
                  {t('需确认')} {draftIssues.length}
                </Tag>
              )}
            </div>
          </Col>
        </Row>
        {renderEffectivePricePanel(editingRow)}
        {hasValue(editingRow.fixedPrice) &&
          (hasValue(editingRow.modelRatio) || hasValue(editingRow.completionRatio)) && (
            <Banner
              type='warning'
              fullMode={false}
              description={t(
                '当前存在固定价格，运行时会优先按次计费；倍率会保留为备选配置，但不会成为当前生效规则。',
              )}
              style={{ marginTop: 12 }}
            />
          )}
      </div>
    );
  };

  const renderEditSourcePanel = () => {
    if (!editingRow) return null;
    const hasQuote =
      editSourceQuote &&
      !editSourceQuote.empty &&
      (editSourceQuote.modelRatio !== undefined ||
        editSourceQuote.completionRatio !== undefined ||
        editSourceQuote.cacheRatio !== undefined);
    const quoteUsdPrices = editSourceQuote?.empty
      ? {}
      : getEquivalentUsdPrices(editSourceQuote || {});

    return (
      <div
        style={{
          border: '1px solid var(--semi-color-border)',
          borderRadius: 8,
          padding: 14,
          marginBottom: 14,
          background: 'var(--semi-color-bg-1)',
        }}
      >
        <Row gutter={16}>
          <Col span={10}>
            <Text strong>{t('价格源参考')}</Text>
            <br />
            <Text type='secondary'>
              {t(
                '从 OpenRouter 拉取当前模型的 token 价，并转换为本站倍率。拉取只做预览，点击回填后仍需确认保存。',
              )}
            </Text>
          </Col>
          <Col span={8}>
            <Text type='secondary'>{t('OpenRouter 模型名')}</Text>
            <Input
              value={editSourceModel}
              placeholder='openai/gpt-4o'
              onChange={(value) => {
                setEditSourceQuote(null);
                setEditSourceModel(value);
              }}
              style={{ marginTop: 6 }}
            />
            <Text type='tertiary'>
              {t('可填本地名或 OpenRouter ID；系统会自动尝试前缀通配匹配。')}
            </Text>
          </Col>
          <Col span={6} style={{ textAlign: 'right' }}>
            <Space>
              <Button
                icon={<IconRefresh />}
                loading={editSourceLoading}
                disabled={!editSourceModel && !editingRow.name}
                onClick={fetchOpenRouterQuoteForEditing}
              >
                {t('拉取')}
              </Button>
              <Button
                type='primary'
                disabled={!hasQuote}
                onClick={applyOpenRouterQuote}
              >
                {t('回填')}
              </Button>
            </Space>
          </Col>
        </Row>
        {editSourceQuote && (
          <div style={{ marginTop: 12 }}>
            {editSourceQuote.empty ? (
              <Text type='secondary'>{editSourceQuote.message}</Text>
            ) : (
              <>
                <Space wrap style={{ marginBottom: 10 }}>
                  <Tag color='blue'>OpenRouter</Tag>
                  <Tag color={editSourceQuote.sameAsCurrent ? 'green' : 'orange'}>
                    {editSourceQuote.sameAsCurrent
                      ? t('当前配置一致')
                      : t('存在可回填差异')}
                  </Tag>
                  {editSourceQuote.sourceMatchedModel &&
                    editSourceQuote.sourceMatchedModel !== editSourceQuote.model && (
                      <Tag color='grey'>
                        {t('OpenRouter 实际模型')}:
                        {editSourceQuote.sourceMatchedModel}
                      </Tag>
                    )}
                  <Tag color='grey'>
                    {t('匹配模型')}：{editSourceQuote.model}
                  </Tag>
                  <Tag color='grey'>
                    {t('分类')}：{editSourceQuote.category || 'text'}
                  </Tag>
                </Space>
                <Row gutter={12}>
                  <Col span={8}>
                    <Text type='secondary'>{t('模型倍率')}</Text>
                    <br />
                    <Text strong>
                      {formatMaybeNumber(editSourceQuote.modelRatio)}
                    </Text>
                    <Text type='secondary'>
                      {' '}
                      ({formatUsdPerMillion(
                        ratioToUsdPerMillion(editSourceQuote.modelRatio),
                      )}
                      )
                    </Text>
                    <br />
                    <Text type='secondary'>
                      {t('输入价')} {formatUsdPerMillion(quoteUsdPrices.inputUsd)}
                    </Text>
                  </Col>
                  <Col span={8}>
                    <Text type='secondary'>{t('补全倍率')}</Text>
                    <br />
                    <Text strong>
                      {formatMaybeNumber(editSourceQuote.completionRatio)}
                    </Text>
                    <br />
                    <Text type='secondary'>
                      {t('输出价')} {formatUsdPerMillion(quoteUsdPrices.outputUsd)}
                    </Text>
                  </Col>
                  <Col span={8}>
                    <Text type='secondary'>{t('缓存倍率')}</Text>
                    <br />
                    <Text strong>
                      {formatMaybeNumber(editSourceQuote.cacheRatio)}
                    </Text>
                    <br />
                    <Text type='secondary'>
                      {t('缓存价')} {formatUsdPerMillion(quoteUsdPrices.cacheUsd)}
                    </Text>
                  </Col>
                </Row>
              </>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderNumberField = ({
    label,
    value,
    onChange,
    suffix,
    placeholder,
    min = 0,
    precision = 8,
  }) => (
    <div style={{ marginBottom: 12 }}>
      <Text type='secondary'>{label}</Text>
      <InputNumber
        value={value}
        min={min}
        precision={precision}
        suffix={suffix}
        placeholder={placeholder}
        style={{ width: '100%', marginTop: 6 }}
        onChange={onChange}
      />
    </div>
  );

  const renderEquivalentUsdEditor = () => {
    if (!editingRow) return null;
    const prices = getEquivalentUsdPrices(editingRow);

    return (
      <div
        style={{
          border: '1px solid var(--semi-color-border)',
          borderRadius: 8,
          padding: 12,
          marginBottom: 12,
          background: 'var(--semi-color-bg-1)',
        }}
      >
        <Row gutter={12} style={{ marginBottom: 10 }}>
          <Col span={24}>
            <Text strong>{t('同等美元编辑')}</Text>
            <Text type='secondary' style={{ marginLeft: 8 }}>
              {t('直接填写 USD/1M tokens；保存时仍写入现有倍率配置。')}
            </Text>
          </Col>
        </Row>
        <Row gutter={12}>
          <Col span={8}>
            {renderNumberField({
              label: t('输入价'),
              value: prices.inputUsd,
              suffix: 'USD/1M',
              onChange: (value) => updateEditingUsdPrice('modelRatio', value),
            })}
          </Col>
          <Col span={8}>
            {renderNumberField({
              label: t('输出价'),
              value: prices.outputUsd,
              suffix: 'USD/1M',
              placeholder: t('先填输入价'),
              onChange: (value) => updateEditingUsdPrice('completionRatio', value),
            })}
          </Col>
          <Col span={8}>
            {renderNumberField({
              label: t('缓存命中价'),
              value: prices.cacheUsd,
              suffix: 'USD/1M',
              placeholder: t('先填输入价'),
              onChange: (value) => updateEditingUsdPrice('cacheRatio', value),
            })}
          </Col>
        </Row>
        <Row gutter={12}>
          <Col span={8}>
            {renderNumberField({
              label: t('图片输入价'),
              value: prices.imageInputUsd,
              suffix: 'USD/1M',
              placeholder: t('先填输入价'),
              onChange: (value) => updateEditingUsdPrice('imageRatio', value),
            })}
          </Col>
          <Col span={8}>
            {renderNumberField({
              label: t('图片输出价'),
              value: prices.imageOutputUsd,
              suffix: 'USD/1M',
              placeholder: t('先填输入价'),
              onChange: (value) =>
                updateEditingUsdPrice('imageCompletionRatio', value),
            })}
          </Col>
          <Col span={8}>
            {renderNumberField({
              label: t('音频输入价'),
              value: prices.audioInputUsd,
              suffix: 'USD/1M',
              placeholder: t('先填输入价'),
              onChange: (value) => updateEditingUsdPrice('audioRatio', value),
            })}
          </Col>
        </Row>
        <Row gutter={12}>
          <Col span={8}>
            {renderNumberField({
              label: t('音频输出价'),
              value: prices.audioOutputUsd,
              suffix: 'USD/1M',
              placeholder: t('先填输入价'),
              onChange: (value) =>
                updateEditingUsdPrice('audioCompletionRatio', value),
            })}
          </Col>
        </Row>
      </div>
    );
  };

  const renderSavePreviewModal = () => {
    if (!savePreview) return null;
    const finalJson = buildEffectiveJsonPreview(savePreview.nextInputs);
    const finalJsonText = JSON.stringify(finalJson, null, 2);
    const changedJson = savePreview.changedKeys.reduce((preview, key) => {
      preview[key] = finalJson[key];
      return preview;
    }, {});
    const changedJsonText = JSON.stringify(changedJson, null, 2);

    return (
      <Modal
        title={t('确认保存价格配置')}
        visible={Boolean(savePreview)}
        onCancel={() => {
          if (!loading) setSavePreview(null);
        }}
        onOk={() => saveInputs(savePreview.nextInputs)}
        okText={t('确认保存')}
        cancelText={t('返回检查')}
        width={980}
        okButtonProps={{ loading }}
        cancelButtonProps={{ disabled: loading }}
      >
        <Space vertical align='start' style={{ width: '100%' }} spacing='medium'>
          <Banner
            type='warning'
            fullMode={false}
            description={t(
              '下面是即将写入后端并生效的最终配置。确认无误后才会保存。',
            )}
          />
          <div>
            <Text type='secondary'>{t('本次变更')}</Text>
            <div style={{ marginTop: 8 }}>
              <Space wrap>
                {savePreview.changedKeys.map((key) => (
                  <Tag color='blue' key={key}>
                    {key}
                  </Tag>
                ))}
              </Space>
            </div>
          </div>
          <Tabs type='line' style={{ width: '100%' }}>
            <Tabs.TabPane tab={t('本次变更 JSON')} itemKey='changed'>
              <pre
                style={{
                  maxHeight: 360,
                  overflow: 'auto',
                  padding: 12,
                  border: '1px solid var(--semi-color-border)',
                  borderRadius: 6,
                  background: 'var(--semi-color-fill-0)',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {changedJsonText}
              </pre>
            </Tabs.TabPane>
            <Tabs.TabPane tab={t('最终生效 JSON')} itemKey='final'>
              <pre
                style={{
                  maxHeight: 420,
                  overflow: 'auto',
                  padding: 12,
                  border: '1px solid var(--semi-color-border)',
                  borderRadius: 6,
                  background: 'var(--semi-color-fill-0)',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {finalJsonText}
              </pre>
            </Tabs.TabPane>
          </Tabs>
        </Space>
      </Modal>
    );
  };

  const renderEditModal = () => (
    <Modal
      title={editingRow?.isNew ? t('添加模型价格') : t('编辑模型价格')}
      visible={Boolean(editingRow)}
      onCancel={() => {
        setEditingRow(null);
        setEditSourceQuote(null);
        setEditSourceModel('');
      }}
      onOk={saveEditingRow}
      okText={t('保存草稿')}
      cancelText={t('取消')}
      width={1040}
    >
      {editingRow && (
        <Form labelPosition='left' labelWidth={120}>
          {renderEditSummaryPanel()}
          {renderEditSourcePanel()}
          <div style={{ marginBottom: 12 }}>
            <Text type='secondary'>{t('模型名称')}</Text>
            <Input
              value={editingRow.name}
              disabled={!editingRow.isNew}
              style={{ marginTop: 6 }}
              onChange={(value) => {
                setEditSourceQuote(null);
                if (!editSourceModel || editSourceModel === editingRow.name) {
                  setEditSourceModel(value);
                }
                setEditingRow((prev) => ({ ...prev, name: value }));
              }}
            />
            <br />
            <Text type='tertiary'>
              {t('新增时可填写模型名；编辑已有模型时保持名称稳定，避免误改键名。')}
            </Text>
          </div>
          {renderBillingModeEditor()}
          <div style={{ display: 'none' }}>
          <Divider margin='12px'>{t('基础计费：固定价或文本倍率')}</Divider>
          <Banner
            type='info'
            fullMode={false}
            description={t(
              '按次固定价适合图片、视频、语音等一次请求固定扣费的模型；文本模型可直接按 USD/1M tokens 编辑，系统会自动换算为倍率。',
            )}
            style={{ marginBottom: 12 }}
          />
          {renderEquivalentUsdEditor()}
          <Text type='secondary'>
            {t('倍率原始值：上方美元价会同步改写这里；也可以直接编辑倍率。')}
          </Text>
          <div style={{ height: 8 }} />
          <Row gutter={12}>
            <Col span={8}>
              {renderNumberField({
                label: t('固定价格'),
                value: editingRow.fixedPrice,
                suffix: 'USD/次',
                onChange: (value) =>
                  setEditingRow((prev) => ({ ...prev, fixedPrice: value })),
              })}
            </Col>
            <Col span={8}>
              {renderNumberField({
                label: t('模型倍率'),
                value: editingRow.modelRatio,
                onChange: (value) =>
                  setEditingRow((prev) => ({ ...prev, modelRatio: value })),
              })}
            </Col>
            <Col span={8}>
              {renderNumberField({
                label: t('补全倍率'),
                value: editingRow.completionRatio,
                onChange: (value) =>
                  setEditingRow((prev) => ({
                    ...prev,
                    completionRatio: value,
                  })),
              })}
            </Col>
          </Row>
          <Divider margin='12px'>{t('多模态倍率：缓存、图片、音频')}</Divider>
          <Row gutter={12}>
            <Col span={8}>
              {renderNumberField({
                label: t('缓存倍率'),
                value: editingRow.cacheRatio,
                onChange: (value) =>
                  setEditingRow((prev) => ({ ...prev, cacheRatio: value })),
              })}
            </Col>
            <Col span={8}>
              {renderNumberField({
                label: t('图片输入倍率'),
                value: editingRow.imageRatio,
                onChange: (value) =>
                  setEditingRow((prev) => ({ ...prev, imageRatio: value })),
              })}
            </Col>
            <Col span={8}>
              {renderNumberField({
                label: t('图片输出倍率'),
                value: editingRow.imageCompletionRatio,
                onChange: (value) =>
                  setEditingRow((prev) => ({
                    ...prev,
                    imageCompletionRatio: value,
                  })),
              })}
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={8}>
              {renderNumberField({
                label: t('音频输入倍率'),
                value: editingRow.audioRatio,
                onChange: (value) =>
                  setEditingRow((prev) => ({ ...prev, audioRatio: value })),
              })}
            </Col>
            <Col span={8}>
              {renderNumberField({
                label: t('音频输出倍率'),
                value: editingRow.audioCompletionRatio,
                onChange: (value) =>
                  setEditingRow((prev) => ({
                    ...prev,
                    audioCompletionRatio: value,
                  })),
              })}
            </Col>
          </Row>
          <Divider margin='12px'>{t('高级规则：分段与条件计费')}</Divider>
          <Banner
            type='warning'
            fullMode={false}
            description={t(
              '分段和条件计费优先级高，通常只在明确知道运行时匹配逻辑时修改。这里保存的是 JSON 规则，建议小步修改后再回到工作台确认校验结果。',
            )}
            style={{ marginBottom: 12 }}
          />
          <Row gutter={12}>
            <Col span={24}>
              <Form.Switch
                label={t('启用分段计费')}
                field='tieredEnabled'
                checked={editingRow.tieredEnabled}
                onChange={(value) =>
                  setEditingRow((prev) => ({ ...prev, tieredEnabled: value }))
                }
              />
              <div
                style={{
                  border: '1px solid var(--semi-color-border)',
                  borderRadius: 8,
                  padding: 12,
                  marginTop: 8,
                  marginBottom: 16,
                }}
              >
                <Row style={{ marginBottom: 10 }} type='flex' align='middle'>
                  <Col span={16}>
                    <Text type='secondary'>
                      {t('按输入 tokens 落入的区间计费；最后一段的最大 tokens 可填 -1，表示无限。')}
                    </Text>
                  </Col>
                  <Col span={8} style={{ textAlign: 'right' }}>
                    <Button icon={<IconPlus />} onClick={addTieredRow}>
                      {t('添加分段')}
                    </Button>
                  </Col>
                </Row>
                <Table
                  size='small'
                  pagination={false}
                  rowKey='index'
                  scroll={{ x: 1320 }}
                  dataSource={(editingRow.tieredTiers || []).map((tier, index) => ({
                    ...tier,
                    index,
                  }))}
                  empty={t('暂无分段，点击“添加分段”创建第一段')}
                  columns={[
                    {
                      title: t('最小 K tokens'),
                      dataIndex: 'min_tokens',
                      width: 130,
                      render: (value, record) => (
                        <InputNumber
                          value={value}
                          min={0}
                          precision={0}
                          style={{ width: '100%' }}
                          onChange={(nextValue) =>
                            updateTieredRow(record.index, 'min_tokens', nextValue)
                          }
                        />
                      ),
                    },
                    {
                      title: t('最大 K tokens'),
                      dataIndex: 'max_tokens',
                      width: 130,
                      render: (value, record) => (
                        <InputNumber
                          value={value}
                          min={-1}
                          precision={0}
                          style={{ width: '100%' }}
                          onChange={(nextValue) =>
                            updateTieredRow(record.index, 'max_tokens', nextValue)
                          }
                        />
                      ),
                    },
                    {
                      title: t('输入价 USD/1M'),
                      dataIndex: 'input_price',
                      width: 150,
                      render: (value, record) => (
                        <InputNumber
                          value={value}
                          min={0}
                          precision={8}
                          style={{ width: '100%' }}
                          onChange={(nextValue) =>
                            updateTieredRow(record.index, 'input_price', nextValue)
                          }
                        />
                      ),
                    },
                    {
                      title: t('输出价 USD/1M'),
                      dataIndex: 'output_price',
                      width: 150,
                      render: (value, record) => (
                        <InputNumber
                          value={value}
                          min={0}
                          precision={8}
                          style={{ width: '100%' }}
                          onChange={(nextValue) =>
                            updateTieredRow(record.index, 'output_price', nextValue)
                          }
                        />
                      ),
                    },
                    {
                      title: t('缓存命中 USD/1M'),
                      dataIndex: 'cache_hit_price',
                      width: 150,
                      render: (value, record) => (
                        <InputNumber
                          value={value}
                          min={0}
                          precision={8}
                          style={{ width: '100%' }}
                          onChange={(nextValue) =>
                            updateTieredRow(record.index, 'cache_hit_price', nextValue)
                          }
                        />
                      ),
                    },
                    {
                      title: t('缓存写入 USD/1M'),
                      dataIndex: 'cache_store_price',
                      width: 150,
                      render: (value, record) => (
                        <InputNumber
                          value={value}
                          min={0}
                          precision={8}
                          style={{ width: '100%' }}
                          onChange={(nextValue) =>
                            updateTieredRow(record.index, 'cache_store_price', nextValue)
                          }
                        />
                      ),
                    },
                    {
                      title: t('写入 5m USD/1M'),
                      dataIndex: 'cache_store_price_5m',
                      width: 150,
                      render: (value, record) => (
                        <InputNumber
                          value={value}
                          min={0}
                          precision={8}
                          style={{ width: '100%' }}
                          onChange={(nextValue) =>
                            updateTieredRow(
                              record.index,
                              'cache_store_price_5m',
                              nextValue,
                            )
                          }
                        />
                      ),
                    },
                    {
                      title: t('写入 1h USD/1M'),
                      dataIndex: 'cache_store_price_1h',
                      width: 150,
                      render: (value, record) => (
                        <InputNumber
                          value={value}
                          min={0}
                          precision={8}
                          style={{ width: '100%' }}
                          onChange={(nextValue) =>
                            updateTieredRow(
                              record.index,
                              'cache_store_price_1h',
                              nextValue,
                            )
                          }
                        />
                      ),
                    },
                    {
                      title: t('操作'),
                      width: 80,
                      render: (_, record) => (
                        <Button
                          type='danger'
                          size='small'
                          icon={<IconDelete />}
                          onClick={() => deleteTieredRow(record.index)}
                        />
                      ),
                    },
                  ]}
                />
              </div>
            </Col>
            <Col span={24}>
              <Divider margin='12px'>{t('条件计费')}</Divider>
            </Col>
            <Col span={24}>
              <Form.Switch
                label={t('启用条件计费')}
                field='conditionalEnabled'
                checked={editingRow.conditionalEnabled}
                onChange={(value) =>
                  setEditingRow((prev) => ({
                    ...prev,
                    conditionalEnabled: value,
                  }))
                }
              />
              <Form.Select
                label={t('条件命中策略')}
                field='conditionalStrategy'
                value={editingRow.conditionalStrategy}
                optionList={[
                  { label: 'first-match', value: 'first-match' },
                  { label: 'max', value: 'max' },
                  { label: 'multiply', value: 'multiply' },
                ]}
                onChange={(value) =>
                  setEditingRow((prev) => ({
                    ...prev,
                    conditionalStrategy: value,
                  }))
                }
              />
              <Form.TextArea
                label={t('条件规则 JSON')}
                field='conditionalRules'
                value={JSON.stringify(editingRow.conditionalRules || [], null, 2)}
                autosize={{ minRows: 5, maxRows: 12 }}
                onChange={(value) => {
                  try {
                    const parsed = JSON.parse(value || '[]');
                    setEditingRow((prev) => ({
                      ...prev,
                      conditionalRules: Array.isArray(parsed) ? parsed : [],
                    }));
                  } catch (error) {
                    showWarning(t('条件规则 JSON 暂未解析成功'));
                  }
                }}
              />
            </Col>
          </Row>
          </div>
        </Form>
      )}
    </Modal>
  );

  return (
    <Spin spinning={loading}>
      <Tabs type='card'>
        <Tabs.TabPane tab={t('价格工作台')} itemKey='workbench'>
          {renderVisualWorkbench()}
        </Tabs.TabPane>
        <Tabs.TabPane tab={t('高级 JSON')} itemKey='advanced'>
          {renderAdvancedEditor()}
        </Tabs.TabPane>
      </Tabs>
      <Divider margin='16px' />
      <Space>
        <Popconfirm
          title={t('确定重置模型倍率吗？')}
          content={t('此修改将不可撤销')}
          okType='danger'
          position='top'
          onConfirm={resetModelRatio}
        >
          <Button type='danger'>{t('重置模型倍率')}</Button>
        </Popconfirm>
      </Space>
      {renderEditModal()}
      {renderSavePreviewModal()}
    </Spin>
  );
}
