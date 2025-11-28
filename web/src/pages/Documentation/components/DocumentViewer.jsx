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

import React, { useState, useEffect } from 'react';
import { Card, Typography, Button, Spin, Empty } from '@douyinfe/semi-ui';
import { IconArrowLeft, IconCopy, IconDownload } from '@douyinfe/semi-icons';
import MarkdownRenderer from '../../../components/common/markdown/MarkdownRenderer';

import overviewContent from '../content/overview.md?raw';
import openaiChatContent from '../content/openai-chat.md?raw';
import openaiResponsesContent from '../content/openai-responses.md?raw';
import examplesContent from '../content/examples.md?raw';
import referenceContent from '../content/reference.md?raw';

const { Title, Text } = Typography;

const DocumentViewer = ({ docKey, onBack }) => {
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const docConfigs = {
    overview: {
      title: 'API 概览',
      content: overviewContent
    },
    'openai-chat': {
      title: 'OpenAI Chat API',
      content: openaiChatContent
    },
    'openai-responses': {
      title: 'OpenAI Responses API',
      content: openaiResponsesContent
    },
    examples: {
      title: '代码示例',
      content: examplesContent
    },
    reference: {
      title: '参考文档',
      content: referenceContent
    }
  };

  useEffect(() => {
    const loadContent = () => {
      if (!docKey) return;

      const config = docConfigs[docKey];
      if (!config) {
        setError('文档不存在');
        return;
      }

      setLoading(true);
      setError(null);

      try {
        if (config.content) {
          setContent(config.content);
        } else {
          setError('文档内容不存在');
        }
      } catch (err) {
        console.error('Failed to load document:', err);
        setError('加载文档失败');
      } finally {
        setLoading(false);
      }
    };

    loadContent();
  }, [docKey]);

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    // 这里可以添加复制成功提示
  };

  const handleDownload = () => {
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${docKey}-documentation.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (!docKey) {
    return (
      <Card className="min-h-[400px]">
        <Empty
          image={<Empty.Image style={{ height: 150 }} />}
          title="请选择要查看的文档"
          description="从左侧导航选择您想要查看的 API 文档部分"
        />
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="min-h-[400px]">
        <div className="text-center py-8">
          <Title heading={5} className="mb-4 text-red-500">
            加载失败
          </Title>
          <Text type="secondary">{error}</Text>
          <div className="mt-6">
            <Button onClick={onBack} icon={<IconArrowLeft />}>
              返回
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card
      className="min-h-[400px]"
      title={
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Button
              icon={<IconArrowLeft />}
              type="tertiary"
              onClick={onBack}
            />
            <Title heading={5} className="mb-0">
              {docConfigs[docKey]?.title || '文档'}
            </Title>
          </div>
          <div className="flex space-x-2">
            <Button
              icon={<IconCopy />}
              type="tertiary"
              onClick={handleCopy}
              size="small"
            >
              复制
            </Button>
            <Button
              icon={<IconDownload />}
              type="tertiary"
              onClick={handleDownload}
              size="small"
            >
              下载
            </Button>
          </div>
        </div>
      }
      bodyStyle={{ padding: 0 }}
    >
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Spin size="large" />
        </div>
      ) : (
        <div className="prose prose-lg max-w-none p-6">
          <MarkdownRenderer content={content} />
        </div>
      )}
    </Card>
  );
};

export default DocumentViewer;