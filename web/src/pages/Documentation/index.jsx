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
import { Layout, Nav, Typography } from '@douyinfe/semi-ui';
import { useTranslation } from 'react-i18next';
import { Route, Routes, useNavigate, useLocation } from 'react-router-dom';
import { IconHome } from '@douyinfe/semi-icons';

import ApiNavigation from './components/ApiNavigation';
import DocumentViewer from './components/DocumentViewer';
import { documentationConfig } from './config';

const { Sider, Content } = Layout;
const { Title, Text } = Typography;

const Documentation = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="min-h-screen bg-gray-50 pt-16">
      <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-8">
          <Title heading={1} className="mb-4">
            {t('API 文档')}
          </Title>
          <Text type="secondary" className="text-lg">
            {t('New API 接口文档和使用说明')}
          </Text>
        </div>

        <Layout className="bg-transparent min-h-[calc(100vh-80px)]">
          <Sider className="bg-transparent mr-6 hidden md:block" style={{ width: 240 }}>
             <div className="bg-white rounded-lg shadow-sm p-2 sticky top-24">
              <Nav
                selectedKeys={[location.pathname]}
                onSelect={(data) => navigate(data.itemKey)}
                style={{ border: 'none' }}
                items={[
                  {
                    itemKey: '/docs',
                    text: '导航概览',
                    icon: <IconHome />,
                  },
                  ...documentationConfig.map(doc => ({
                    itemKey: doc.path,
                    text: doc.title,
                    icon: doc.icon
                  }))
                ]}
              />
             </div>
          </Sider>
          <Content>
            <Routes>
              <Route index element={<ApiNavigation />} />
              {documentationConfig.map(doc => (
                <Route
                  key={doc.key}
                  path={doc.key}
                  element={<DocumentViewer doc={doc} />}
                />
              ))}
            </Routes>
          </Content>
        </Layout>
      </div>
    </div>
  );
};

export default Documentation;