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
import { Card, Typography, Button } from '@douyinfe/semi-ui';
import { IconCopy } from '@douyinfe/semi-icons';
import { useTranslation } from 'react-i18next';
import MarkdownRenderer from '../../../components/common/markdown/MarkdownRenderer';

const { Title } = Typography;

const DocumentViewer = ({ doc }) => {
  const { t, i18n } = useTranslation();

  const getContent = () => {
    if (!doc?.content) return '';
    if (typeof doc.content === 'string') return doc.content;
    
    const lang = i18n.language;
    if (doc.content[lang]) return doc.content[lang];
    
    // Fallback for specific language codes (e.g. zh-CN -> zh)
    const shortLang = lang.split('-')[0];
    if (doc.content[shortLang]) return doc.content[shortLang];
    
    // Default fallback
    return doc.content.zh || doc.content.en || Object.values(doc.content)[0] || '';
  };

  const handleCopy = () => {
    const content = getContent();
    if (content) {
      navigator.clipboard.writeText(content);
      // 这里可以添加复制成功提示
    }
  };

  if (!doc) {
    return null;
  }

  return (
    <Card
      className="min-h-[400px]"
      title={
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Title heading={5} className="mb-0">
              {t(doc.title) || t('doc.document')}
            </Title>
          </div>
          <div className="flex space-x-2">
            <Button
              icon={<IconCopy />}
              type="tertiary"
              onClick={handleCopy}
              size="small"
            >
              {t('复制')}
            </Button>
          </div>
        </div>
      }
      bodyStyle={{ padding: 0 }}
    >
      <div className="prose prose-lg max-w-none p-6">
        <MarkdownRenderer content={getContent()} defaultExpanded={true} />
      </div>
    </Card>
  );
};

export default DocumentViewer;