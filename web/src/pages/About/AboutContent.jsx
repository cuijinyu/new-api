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
import { Typography } from '@douyinfe/semi-ui';
import {
  IconBolt,
  IconKey,
  IconRefresh,
  IconPriceTag,
  IconCheckCircleStroked,
} from '@douyinfe/semi-icons';

const { Title, Text, Paragraph } = Typography;

// 特性卡片组件
const FeatureCard = ({ icon, title, description, isLeft }) => (
  <div className={`flex gap-6 items-start ${isLeft ? 'flex-row' : 'flex-row-reverse text-right'}`}>
    <div className='flex-shrink-0 w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500/20 to-cyan-500/20 flex items-center justify-center'>
      {icon}
    </div>
    <div className='flex-1'>
      <h4 className='text-lg font-semibold text-semi-color-text-0 mb-2'>{title}</h4>
      <p className='text-semi-color-text-2 leading-relaxed'>{description}</p>
    </div>
  </div>
);

// 承诺卡片组件
const CommitmentCard = ({ icon, title, description }) => (
  <div className='p-6 rounded-2xl bg-semi-color-bg-1 border border-semi-color-border hover:shadow-lg transition-all duration-300'>
    <div className='flex items-center gap-4 mb-3'>
      <div className='w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500/20 to-teal-500/20 flex items-center justify-center'>
        {icon}
      </div>
      <h4 className='text-lg font-semibold text-semi-color-text-0'>{title}</h4>
    </div>
    <p className='text-semi-color-text-2 text-sm leading-relaxed'>{description}</p>
  </div>
);

const AboutContent = () => {
  return (
    <div className='w-full min-h-screen bg-semi-color-bg-0'>
      {/* Hero Section */}
      <section className='relative py-20 px-4 overflow-hidden'>
        <div className='absolute inset-0 ez-hero-bg opacity-50' />
        <div className='relative z-10 max-w-4xl mx-auto text-center'>
          <h1 className='text-5xl md:text-6xl font-black tracking-tight mb-6'>
            <span className='ez-brand-text'>EZ</span>
            <span className='text-semi-color-text-0'>model</span>
          </h1>
          <p className='text-xl md:text-2xl text-semi-color-text-1 mb-4'>
            One API, All AI Models
          </p>
          <p className='text-lg text-semi-color-text-2'>
            Abstract the complexity, focus on building great products
          </p>
        </div>
      </section>

      {/* What We Do Section */}
      <section className='py-16 px-4 bg-semi-color-bg-1'>
        <div className='max-w-4xl mx-auto'>
          <div className='text-center mb-12'>
            <h2 className='text-3xl md:text-4xl font-bold text-semi-color-text-0 mb-4'>
              我们在做什么？
            </h2>
            <p className='text-lg text-semi-color-text-2'>What We Do</p>
          </div>
          <div className='p-8 rounded-3xl bg-semi-color-bg-0 shadow-lg'>
            <Paragraph className='text-lg text-semi-color-text-1 leading-relaxed'>
              EZmodel 是一个领先的 <Text strong>MaaS (Model-as-a-Service)</Text> 聚合平台。
              我们通过统一的 OpenAI 标准协议，无缝接入全球主流大语言模型，
              帮助企业与开发者降低 <Text strong className='ez-brand-text'>90% 以上</Text> 的集成与维护成本。
            </Paragraph>
          </div>
        </div>
      </section>

      {/* Vision Section */}
      <section className='py-16 px-4 bg-semi-color-bg-0'>
        <div className='max-w-4xl mx-auto'>
          <div className='text-center mb-12'>
            <h2 className='text-3xl md:text-4xl font-bold text-semi-color-text-0 mb-4'>
              核心愿景
            </h2>
            <p className='text-lg text-semi-color-text-2'>The Vision</p>
          </div>
          <div className='relative p-10 rounded-3xl bg-gradient-to-br from-blue-500/10 via-purple-500/10 to-cyan-500/10 border border-semi-color-border'>
            <div className='absolute top-4 left-4 text-6xl text-semi-color-text-3 opacity-20'>"</div>
            <div className='text-center'>
              <p className='text-2xl md:text-3xl font-medium text-semi-color-text-0 mb-4 leading-relaxed'>
                消除智能鸿沟，让每一颗创造的心不被技术阻隔。
              </p>
              <p className='text-lg text-semi-color-text-2 italic'>
                Bridging the AI gap, empowering every creative mind.
              </p>
            </div>
            <div className='absolute bottom-4 right-4 text-6xl text-semi-color-text-3 opacity-20'>"</div>
          </div>
        </div>
      </section>

      {/* Why EZmodel Section */}
      <section className='py-16 px-4 bg-semi-color-bg-1'>
        <div className='max-w-5xl mx-auto'>
          <div className='text-center mb-16'>
            <h2 className='text-3xl md:text-4xl font-bold text-semi-color-text-0 mb-4'>
              为什么选择我们？
            </h2>
            <p className='text-lg text-semi-color-text-2'>Why EZmodel</p>
          </div>
          
          <div className='grid md:grid-cols-2 gap-12 items-center'>
            {/* Left Feature */}
            <FeatureCard
              icon={<IconBolt size='extra-large' className='text-blue-500' />}
              title='先行者优势：首发模型，即刻触达'
              description='我们与全球顶级模型厂商深度合作，确保新模型上线即首发。在 EZmodel，你永远是第一批体验下一代 AI 能力的开发者，无需等待，无需排队。'
              isLeft={true}
            />
            
            {/* Right Feature */}
            <FeatureCard
              icon={<IconKey size='extra-large' className='text-emerald-500' />}
              title='统一密钥方案：单一 API Key，调度全网智能'
              description='告别维护数十个平台密钥的烦恼。只需一个 EZmodel API Key，即可在所有顶级模型间无缝切换，彻底简化你的鉴权逻辑与账单管理。'
              isLeft={true}
            />
          </div>
        </div>
      </section>

      {/* Our Commitment Section */}
      <section className='py-16 px-4 bg-semi-color-bg-0'>
        <div className='max-w-5xl mx-auto'>
          <div className='text-center mb-16'>
            <h2 className='text-3xl md:text-4xl font-bold text-semi-color-text-0 mb-4'>
              技术承诺
            </h2>
            <p className='text-lg text-semi-color-text-2'>Our Commitment</p>
          </div>
          
          <div className='grid md:grid-cols-3 gap-6'>
            <CommitmentCard
              icon={<IconRefresh size='large' className='text-blue-500' />}
              title='极速上线'
              description='厂商级首发合作，同步最新 AI 浪潮。'
            />
            <CommitmentCard
              icon={<IconCheckCircleStroked size='large' className='text-emerald-500' />}
              title='极致统一'
              description='标准 OpenAI 协议，无感知平滑切换。'
            />
            <CommitmentCard
              icon={<IconPriceTag size='large' className='text-orange-500' />}
              title='极简计费'
              description='场景化订阅模式，成本透明，预算可控。'
            />
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className='py-20 px-4 ez-cta-section'>
        <div className='max-w-4xl mx-auto text-center'>
          <h2 className='text-3xl md:text-4xl font-bold text-semi-color-text-0 mb-6'>
            准备好开始了吗？
          </h2>
          <p className='text-lg text-semi-color-text-2 mb-8'>
            立即注册，开启您的 AI 之旅
          </p>
          <a
            href='/register'
            className='inline-block px-10 py-4 rounded-full text-lg font-semibold text-white ez-cta-btn transition-all duration-300 hover:scale-105'
          >
            免费开始使用
          </a>
        </div>
      </section>
    </div>
  );
};

export default AboutContent;
