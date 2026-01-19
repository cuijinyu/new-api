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
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { documentationConfig } from '../config';

const { Title, Text } = Typography;

const ApiNavigation = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const categories = [
    { key: 'getting-started', title: 'doc.category.gettingStarted' },
    { key: 'chat', title: 'doc.category.chat' },
    { key: 'image', title: 'doc.category.image' },
    { key: 'video', title: 'doc.category.video' },
    { key: 'audio', title: 'doc.category.audio' },
  ];

  const groupedDocs = categories.map(cat => ({
    ...cat,
    docs: documentationConfig.filter(doc => doc.category === cat.key)
  })).filter(cat => cat.docs.length > 0);

  return (
    <div className="space-y-8">
      <Card
        bodyStyle={{ padding: '24px' }}
      >
        <div className="mb-6">
          <Title heading={4} className="mb-2">
            📚 {t('doc.nav.title')}
          </Title>
          <Text type="secondary" size="small">
            {t('doc.nav.desc')}
          </Text>
        </div>

        <div className="space-y-8">
          {groupedDocs.map(category => (
            <div key={category.key}>
              <Title heading={5} className="mb-4 text-gray-700">
                {t(category.title)}
              </Title>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {category.docs.map((doc) => (
                  <Card
                    key={doc.key}
                    className="cursor-pointer transition-all duration-200 hover:shadow-md hover:border-blue-500 hover:bg-blue-50"
                    bodyStyle={{ padding: '16px' }}
                    onClick={() => navigate(doc.path)}
                  >
                    <div className="flex items-start space-x-3">
                      <div className="mt-1 text-blue-500">
                        {doc.icon}
                      </div>
                      <div className="flex-1">
                        <Title heading={6} className="mb-1">
                          {t(doc.title)}
                        </Title>
                        <Text type="secondary" size="small">
                          {t(doc.description)}
                        </Text>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};

export default ApiNavigation;