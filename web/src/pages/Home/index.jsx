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

import React, { useContext, useEffect, useState } from 'react';
import { Button, Typography } from '@douyinfe/semi-ui';
import { API, showError, copy, showSuccess } from '../../helpers';
import { useIsMobile } from '../../hooks/common/useIsMobile';
import { StatusContext } from '../../context/Status';
import { useActualTheme } from '../../context/Theme';
import { marked } from 'marked';
import { useTranslation } from 'react-i18next';
import {
  IconGithubLogo,
  IconArrowRight,
  IconCopy,
  IconCustomerSupport,
  IconEdit,
  IconSearch,
  IconImage,
  IconBolt,
  IconPriceTag,
  IconRefresh,
  IconLineChartStroked,
  IconMail,
} from '@douyinfe/semi-icons';
import { Link } from 'react-router-dom';
import NoticeModal from '../../components/layout/NoticeModal';
import {
  OpenAI,
  Claude,
  Gemini,
  Grok,
  DeepSeek,
  Doubao,
  Kling,
} from '@lobehub/icons';

const { Text } = Typography;

// 使用场景卡片
const UseCaseCard = ({ icon, title, description, gradient }) => (
  <div className={`relative p-6 rounded-3xl overflow-hidden group cursor-pointer transition-all duration-500 hover:scale-[1.02] hover:shadow-2xl ${gradient}`}>
    <div className='relative z-10'>
      <div className='w-12 h-12 rounded-xl bg-white/20 flex items-center justify-center mb-4'>
        {icon}
      </div>
      <h3 className='text-xl font-bold text-white mb-2'>{title}</h3>
      <p className='text-white/80 text-sm leading-relaxed'>{description}</p>
    </div>
    <div className='absolute inset-0 bg-gradient-to-t from-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300' />
  </div>
);

// 步骤组件
const StepItem = ({ number, title, description }) => (
  <div className='flex gap-4'>
    <div className='flex-shrink-0 w-10 h-10 rounded-full ez-step-circle flex items-center justify-center text-white font-bold text-lg'>
      {number}
    </div>
    <div>
      <h4 className='text-lg font-semibold text-semi-color-text-0 mb-1'>{title}</h4>
      <p className='text-semi-color-text-2 text-sm'>{description}</p>
    </div>
  </div>
);

// 模型图标横幅
const ModelIconBanner = () => {
  const icons = [
    // 文生图/视频供应商前置
    <Kling.Color key='kling' size={32} />,
    // 大语言模型
    <OpenAI key='openai' size={32} />,
    <Claude.Color key='claude' size={32} />,
    <Gemini.Color key='gemini' size={32} />,
    <Grok key='grok' size={32} />,
    <DeepSeek.Color key='deepseek' size={32} />,
    <Doubao.Color key='doubao' size={32} />,
  ];

  return (
    <div className='flex items-center justify-center gap-6 md:gap-8 flex-wrap opacity-60'>
      {icons.map((icon, index) => (
        <div key={index} className='transition-transform hover:scale-110'>
          {icon}
        </div>
      ))}
    </div>
  );
};

const Home = () => {
  const { t, i18n } = useTranslation();
  const [statusState] = useContext(StatusContext);
  const actualTheme = useActualTheme();
  const [homePageContentLoaded, setHomePageContentLoaded] = useState(false);
  const [homePageContent, setHomePageContent] = useState('');
  const [noticeVisible, setNoticeVisible] = useState(false);
  const isMobile = useIsMobile();
  const isDemoSiteMode = statusState?.status?.demo_site_enabled || false;

  const headerNavModulesConfig = statusState?.status?.HeaderNavModules;
  let headerNavModules;
  try {
    headerNavModules = headerNavModulesConfig
      ? JSON.parse(headerNavModulesConfig)
      : { home: true, console: true, pricing: true, docs: true, about: true };
  } catch (error) {
    headerNavModules = { home: true, console: true, pricing: true, docs: true, about: true };
  }

  const serverAddress = statusState?.status?.server_address || `${window.location.origin}`;
  const isChinese = i18n.language.startsWith('zh');

  const displayHomePageContent = async () => {
    setHomePageContent(localStorage.getItem('home_page_content') || '');
    const res = await API.get('/api/home_page_content');
    const { success, message, data } = res.data;
    if (success) {
      let content = data;
      if (!data.startsWith('https://')) {
        content = marked.parse(data);
      }
      setHomePageContent(content);
      localStorage.setItem('home_page_content', content);

      if (data.startsWith('https://')) {
        const iframe = document.querySelector('iframe');
        if (iframe) {
          iframe.onload = () => {
            iframe.contentWindow.postMessage({ themeMode: actualTheme }, '*');
            iframe.contentWindow.postMessage({ lang: i18n.language }, '*');
          };
        }
      }
    } else {
      showError(message);
      setHomePageContent('加载首页内容失败...');
    }
    setHomePageContentLoaded(true);
  };

  const handleCopyURL = async () => {
    const ok = await copy(`${serverAddress}/v1`);
    if (ok) {
      showSuccess(t('已复制到剪切板'));
    }
  };

  useEffect(() => {
    const checkNoticeAndShow = async () => {
      const lastCloseDate = localStorage.getItem('notice_close_date');
      const today = new Date().toDateString();
      if (lastCloseDate !== today) {
        try {
          const res = await API.get('/api/notice');
          const { success, data } = res.data;
          if (success && data && data.trim() !== '') {
            setNoticeVisible(true);
          }
        } catch (error) {
          console.error('获取公告失败:', error);
        }
      }
    };
    checkNoticeAndShow();
  }, []);

  useEffect(() => {
    displayHomePageContent().then();
  }, []);

  // 使用场景数据
  const useCases = [
    {
      icon: <IconCustomerSupport size='extra-large' className='text-white' />,
      title: t('智能客服'),
      description: t('构建7×24小时在线的AI客服系统，提升客户满意度'),
      gradient: 'bg-gradient-to-br from-blue-500 to-cyan-400',
    },
    {
      icon: <IconEdit size='extra-large' className='text-white' />,
      title: t('内容创作'),
      description: t('AI辅助文案撰写、翻译、摘要生成，提高创作效率'),
      gradient: 'bg-gradient-to-br from-teal-500 to-emerald-400',
    },
    {
      icon: <IconSearch size='extra-large' className='text-white' />,
      title: t('知识问答'),
      description: t('基于企业知识库的智能问答系统，赋能员工与客户'),
      gradient: 'bg-gradient-to-br from-sky-500 to-indigo-400',
    },
    {
      icon: <IconImage size='extra-large' className='text-white' />,
      title: t('图像生成'),
      description: t('AI驱动的创意设计，快速生成营销素材与产品图'),
      gradient: 'bg-gradient-to-br from-orange-500 to-amber-400',
    },
  ];

  return (
    <div className='w-full overflow-x-hidden'>
      <NoticeModal
        visible={noticeVisible}
        onClose={() => setNoticeVisible(false)}
        isMobile={isMobile}
      />
      {homePageContentLoaded && homePageContent === '' ? (
        <div className='w-full overflow-x-hidden'>
          {/* ========== Hero Section ========== */}
          <section className='relative min-h-screen flex items-center justify-center overflow-hidden'>
            {/* 动态背景 */}
            <div className='absolute inset-0 ez-hero-bg' />
            
            {/* 渐变遮罩 */}
            <div className='absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-semi-color-bg-0' />

            <div className='relative z-10 max-w-5xl mx-auto px-4 py-32 text-center'>
              {/* Logo/品牌名 */}
              <div className='mb-8'>
                <h1 className='text-6xl md:text-7xl lg:text-8xl font-black tracking-tight'>
                  <span className='ez-brand-text'>EZ</span>
                  <span className='text-semi-color-text-0'>model</span>
                </h1>
              </div>

              {/* 主标语 */}
              <h2 className={`text-2xl md:text-3xl lg:text-4xl font-medium text-semi-color-text-0 mb-6 ${isChinese ? 'tracking-wider' : ''}`}>
                {t('一个接口，所有AI模型')}
              </h2>

              {/* 副标语 */}
              <p className='text-lg md:text-xl text-semi-color-text-2 mb-12 max-w-2xl mx-auto leading-relaxed'>
                {t('像调用GPT一样简单地使用Claude、Gemini、DeepSeek等全球顶尖AI模型')}
              </p>

              {/* CTA 按钮组 */}
              <div className='flex flex-col sm:flex-row gap-4 justify-center items-center mb-16'>
                <Link to='/register'>
                  <Button
                    theme='solid'
                    size='large'
                    className='!rounded-full !px-10 !py-3 !text-lg ez-cta-btn'
                  >
                    {t('立即体验')}
                    <IconArrowRight className='ml-2' />
                  </Button>
                </Link>
                {headerNavModules.docs && (
                  <Link to='/docs'>
                    <Button
                      theme='borderless'
                      size='large'
                      className='!rounded-full !px-8 !py-3 !text-lg text-semi-color-text-1 hover:text-semi-color-text-0'
                    >
                      {t('阅读文档')}
                    </Button>
                  </Link>
                )}
                {isDemoSiteMode && statusState?.status?.version && (
                  <Button
                    theme='borderless'
                    size='large'
                    className='!rounded-full !px-6 !py-3'
                    icon={<IconGithubLogo />}
                    onClick={() => {}}
                  >
                    {statusState.status.version}
                  </Button>
                )}
              </div>

              {/* 模型图标横幅 */}
              <ModelIconBanner />
            </div>
          </section>

          {/* ========== API 展示区 ========== */}
          <section className='py-20 px-4 bg-semi-color-bg-0'>
            <div className='max-w-4xl mx-auto'>
              <div className='text-center mb-12'>
                <h2 className='text-3xl md:text-4xl font-bold text-semi-color-text-0 mb-4'>
                  {t('三行代码，即刻接入')}
                </h2>
                <p className='text-semi-color-text-2 text-lg'>
                  {t('完全兼容 OpenAI SDK，无需学习新的 API')}
                </p>
              </div>

              <div className='ez-code-block rounded-2xl overflow-hidden shadow-lg'>
                <div className='ez-code-header flex items-center justify-between px-4 py-3'>
                  <div className='flex gap-2'>
                    <div className='w-3 h-3 rounded-full bg-red-400' />
                    <div className='w-3 h-3 rounded-full bg-yellow-400' />
                    <div className='w-3 h-3 rounded-full bg-green-400' />
                  </div>
                  <span className='text-semi-color-text-2 text-sm font-medium'>Python</span>
                  <Button
                    theme='borderless'
                    size='small'
                    icon={<IconCopy />}
                    onClick={handleCopyURL}
                    className='text-semi-color-text-2 hover:text-semi-color-text-0'
                  />
                </div>
                <pre className='p-6 text-sm md:text-base overflow-x-auto'>
                  <code>
                    <span className='code-keyword'>from</span>
                    <span className='code-text'> openai </span>
                    <span className='code-keyword'>import</span>
                    <span className='code-text'> OpenAI</span>
                    {'\n\n'}
                    <span className='code-text'>client = OpenAI(</span>
                    {'\n'}
                    <span className='code-text'>    base_url=</span>
                    <span className='code-string'>"{serverAddress}/v1"</span>
                    <span className='code-comment'>  # {t('只需修改这里')}</span>
                    {'\n'}
                    <span className='code-text'>)</span>
                  </code>
                </pre>
              </div>
            </div>
          </section>

          {/* ========== 使用场景 ========== */}
          <section className='py-20 px-4 bg-semi-color-bg-1'>
            <div className='max-w-6xl mx-auto'>
              <div className='text-center mb-16'>
                <h2 className='text-3xl md:text-4xl font-bold text-semi-color-text-0 mb-4'>
                  {t('赋能无限场景')}
                </h2>
                <p className='text-semi-color-text-2 text-lg'>
                  {t('从创意到生产，AI 能力触手可及')}
                </p>
              </div>

              <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6'>
                {useCases.map((useCase, index) => (
                  <UseCaseCard key={index} {...useCase} />
                ))}
              </div>
            </div>
          </section>

          {/* ========== 如何开始 ========== */}
          <section className='py-20 px-4 bg-semi-color-bg-0'>
            <div className='max-w-4xl mx-auto'>
              <div className='text-center mb-16'>
                <h2 className='text-3xl md:text-4xl font-bold text-semi-color-text-0 mb-4'>
                  {t('三步开始')}
                </h2>
                <p className='text-semi-color-text-2 text-lg'>
                  {t('几分钟内即可完成接入')}
                </p>
              </div>

              <div className='grid md:grid-cols-3 gap-8'>
                <StepItem
                  number='1'
                  title={t('注册账号')}
                  description={t('免费注册')}
                />
                <StepItem
                  number='2'
                  title={t('获取密钥')}
                  description={t('在控制台创建 API Key')}
                />
                <StepItem
                  number='3'
                  title={t('开始调用')}
                  description={t('修改 base_url 即可使用')}
                />
              </div>

              <div className='text-center mt-12'>
                <Link to='/register'>
                  <Button
                    theme='solid'
                    size='large'
                    className='!rounded-full !px-10 !py-3 ez-cta-btn'
                  >
                    {t('免费开始')}
                  </Button>
                </Link>
              </div>
            </div>
          </section>

          {/* ========== 为什么选择我们 ========== */}
          <section className='py-20 px-4 bg-semi-color-bg-1'>
            <div className='max-w-6xl mx-auto'>
              {/* 标题区域 */}
              <div className='text-center mb-16'>
                <h2 className='text-3xl md:text-4xl font-bold text-semi-color-text-0 mb-4'>
                  {t('为什么选择我们?')}
                </h2>
                <p className='text-semi-color-text-2 text-lg'>
                  Why EZmodel
                </p>
              </div>

              {/* 特性列表 - 图标统一在左侧 */}
              <div className='space-y-12 max-w-3xl mx-auto'>
                <div className='flex gap-6'>
                  <div className='flex-shrink-0 w-16 h-16 rounded-2xl bg-gradient-to-br from-orange-500/20 to-amber-500/20 flex items-center justify-center'>
                    <IconRefresh size='extra-large' className='text-orange-500' />
                  </div>
                  <div>
                    <h4 className='text-xl font-semibold text-semi-color-text-0 mb-2'>{t('智能切换')}</h4>
                    <p className='text-semi-color-text-2 leading-relaxed'>{t('自动负载均衡，故障无感切换')}</p>
                  </div>
                </div>
                
                <div className='flex gap-6'>
                  <div className='flex-shrink-0 w-16 h-16 rounded-2xl bg-gradient-to-br from-sky-500/20 to-blue-500/20 flex items-center justify-center'>
                    <IconLineChartStroked size='extra-large' className='text-sky-500' />
                  </div>
                  <div>
                    <h4 className='text-xl font-semibold text-semi-color-text-0 mb-2'>{t('透明账单')}</h4>
                    <p className='text-semi-color-text-2 leading-relaxed'>{t('详细的用量统计与成本分析')}</p>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* ========== 技术承诺 ========== */}
          <section className='py-20 px-4 bg-semi-color-bg-0'>
            <div className='max-w-6xl mx-auto'>
              <div className='text-center mb-16'>
                <h2 className='text-3xl md:text-4xl font-bold text-semi-color-text-0 mb-4'>
                  {t('技术承诺')}
                </h2>
                <p className='text-semi-color-text-2 text-lg'>
                  Our Commitment
                </p>
              </div>

              <div className='grid md:grid-cols-2 gap-8 max-w-4xl mx-auto'>
                <div className='ez-feature-card p-8 rounded-3xl'>
                  <div className='text-center'>
                    <div className='text-5xl md:text-6xl font-bold ez-brand-text mb-2'>{t('低至官方')}</div>
                    <div className='text-4xl md:text-5xl font-bold text-semi-color-text-0 mb-2'>{t('5折')}</div>
                    <div className='text-semi-color-text-2'>{t('同等质量，更优价格')}</div>
                  </div>
                </div>
                
                <div className='grid grid-cols-2 gap-4'>
                  <div className='p-6 rounded-xl bg-semi-color-bg-1'>
                    <div className='text-3xl font-bold text-semi-color-text-0 mb-1'>{t('零')}</div>
                    <div className='text-sm text-semi-color-text-2'>{t('最低消费')}</div>
                  </div>
                  <div className='p-6 rounded-xl bg-semi-color-bg-1'>
                    <div className='text-3xl font-bold text-semi-color-text-0 mb-1'>{t('实时')}</div>
                    <div className='text-sm text-semi-color-text-2'>{t('用量结算')}</div>
                  </div>
                  <div className='p-6 rounded-xl bg-semi-color-bg-1 col-span-2'>
                    <div className='text-3xl font-bold text-semi-color-text-0 mb-1'>99.9%</div>
                    <div className='text-sm text-semi-color-text-2'>{t('服务可用性')}</div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* ========== CTA Section ========== */}
          <section className='py-24 px-4 ez-cta-section'>
            <div className='max-w-4xl mx-auto text-center relative z-10'>
              <h2 className='text-3xl md:text-4xl font-bold text-semi-color-text-0 mb-6'>
                {t('准备好开始了吗？')}
              </h2>
              <p className='text-semi-color-text-2 text-lg mb-10'>
                {t('注册即获免费额度，立即体验 AI 的强大能力')}
              </p>
              
              <div className='flex flex-col sm:flex-row gap-4 justify-center items-center mb-12'>
                <Link to='/register'>
                  <Button
                    theme='solid'
                    size='large'
                    className='!rounded-full !px-12 !py-4 !text-lg ez-cta-btn'
                  >
                    {t('免费注册')}
                  </Button>
                </Link>
                {headerNavModules.pricing && (
                  <Link to='/pricing'>
                    <Button
                      theme='outline'
                      size='large'
                      className='!rounded-full !px-8 !py-4 !text-lg !font-semibold'
                    >
                      {t('查看定价')}
                    </Button>
                  </Link>
                )}
              </div>

              {/* 联系方式 */}
              <div className='flex flex-col sm:flex-row gap-4 justify-center items-center max-w-2xl mx-auto'>
                {/* Discord - 个人充值付费 */}
                <div className='ez-contact-card rounded-2xl p-5 flex-1 w-full sm:w-auto'>
                  <div className='flex items-center gap-4'>
                    <div className='w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center flex-shrink-0'>
                      <svg className='w-6 h-6 text-white' viewBox='0 0 24 24' fill='currentColor'>
                        <path d='M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z'/>
                      </svg>
                    </div>
                    <div className='text-left min-w-0'>
                      <div className='text-sm text-semi-color-text-2 mb-0.5'>{t('个人充值付费及问题咨询')}</div>
                      <a 
                        href='https://discord.com/invite/4uMKXdspAh' 
                        target='_blank'
                        rel='noopener noreferrer'
                        className='text-semi-color-primary font-medium hover:underline truncate block'
                      >
                        Discord
                      </a>
                    </div>
                  </div>
                </div>
                
                {/* 企业邮箱 */}
                <div className='ez-contact-card rounded-2xl p-5 flex-1 w-full sm:w-auto'>
                  <div className='flex items-center gap-4'>
                    <div className='w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center flex-shrink-0'>
                      <IconMail size='extra-large' className='text-white' />
                    </div>
                    <div className='text-left min-w-0'>
                      <div className='text-sm text-semi-color-text-2 mb-0.5'>{t('企业接入咨询')}</div>
                      <a 
                        href='mailto:service@ezmodel.cloud' 
                        className='text-semi-color-primary font-medium hover:underline truncate block'
                      >
                        service@ezmodel.cloud
                      </a>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      ) : (
        <div className='overflow-x-hidden w-full'>
          {homePageContent.startsWith('https://') ? (
            <iframe
              src={homePageContent}
              className='w-full h-screen border-none'
            />
          ) : (
            <div
              className='mt-[60px]'
              dangerouslySetInnerHTML={{ __html: homePageContent }}
            />
          )}
        </div>
      )}
    </div>
  );
};

export default Home;
