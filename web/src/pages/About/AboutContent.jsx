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
              EZmodel is a premier <Text strong>Model-as-a-Service (MaaS)</Text> aggregation layer. By delivering a consolidated interface via OpenAI-standard protocols, we enable seamless orchestration of global LLMs. Our infrastructure reduces integration overhead and maintenance complexity by over <Text strong className='ez-brand-text'>90%</Text> for enterprises and developers alike.
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
              title='First-to-Market Advantage: Zero-Day Deployment'
              description='Through deep strategic partnerships with global model providers, we guarantee Day 0 availability for SOTA (State-of-the-Art) models. With EZmodel, you gain immediate access to next-generation AI capabilities—no waitlists, no latency in adoption.'
              isLeft={true}
            />
            
            {/* Right Feature */}
            <FeatureCard
              icon={<IconKey size='extra-large' className='text-emerald-500' />}
              title='Unified Credentialing: Single API Key, Universal Intelligence'
              description='Eliminate the friction of managing fragmented credentials across multiple providers. A single EZmodel API Key grants you the power to switch between top-tier models instantaneously, radically simplifying your authentication logic and billing management.'
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
              title='Agile Integration'
              description='Partner-level early access ensuring your tech stack evolves in sync with the global AI frontier.'
            />
            <CommitmentCard
              icon={<IconCheckCircleStroked size='large' className='text-emerald-500' />}
              title='Unified Architecture'
              description='100% OpenAI-standard compatibility for transparent, zero-refactor model switching.'
            />
            <CommitmentCard
              icon={<IconPriceTag size='large' className='text-orange-500' />}
              title='Optimized Billing'
              description='Scenario-based subscription plans designed for transparent cost-tracking and granular budget control.'
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
