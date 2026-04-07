'use client';

import Link from 'next/link';
import Sidebar from '@/components/Sidebar';
import { useLanguage } from '@/lib/contexts';
import { withDemoQuery } from '@/lib/demoMode';

export default function SampleCasesPage() {
  const { t } = useLanguage();

  const cards = [
    {
      icon: '📤',
      title: t('sampleCases.card1Title'),
      desc: t('sampleCases.card1Desc'),
      eta: t('sampleCases.card1Eta'),
      ctaHref: withDemoQuery('/dashboard/upload', true),
      ctaLabel: t('dashboard.uploadEvidence'),
    },
    {
      icon: '📝',
      title: t('sampleCases.card2Title'),
      desc: t('sampleCases.card2Desc'),
      eta: t('sampleCases.card2Eta'),
      ctaHref: '/dashboard/assessments',
      ctaLabel: t('dashboard.assessments'),
    },
    {
      icon: '🎯',
      title: t('sampleCases.card3Title'),
      desc: t('sampleCases.card3Desc'),
      eta: t('sampleCases.card3Eta'),
      ctaHref: withDemoQuery('/dashboard/jobs', true),
      ctaLabel: t('dashboard.jobs'),
    },
  ];

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">🧪 {t('sampleCases.pageTitle')}</h1>
            <p className="page-subtitle">{t('sampleCases.pageSubtitle')}</p>
          </div>
          <div className="page-actions">
            <Link href="/dashboard" className="btn btn-ghost btn-sm">
              {t('common.back')}
            </Link>
          </div>
        </div>

        <div className="page-content">
          <div className="card" style={{ border: '1px solid var(--gray-200)', marginBottom: '1rem' }}>
            <div className="card-content" style={{ padding: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
              <div>
                <h2 style={{ fontSize: '1rem', marginBottom: '0.25rem' }}>{t('sampleCases.quickTourTitle')}</h2>
                <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--gray-600)' }}>{t('sampleCases.quickTourDesc')}</p>
              </div>
              <Link href={withDemoQuery('/dashboard/upload', true)} className="btn btn-primary btn-sm">
                {t('sampleCases.startTour')}
              </Link>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
            {cards.map((card) => (
              <div key={card.title} className="card" style={{ border: '1px solid var(--gray-200)' }}>
                <div className="card-content" style={{ padding: '1rem' }}>
                  <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>{card.icon}</div>
                  <h3 style={{ marginBottom: '0.5rem', fontSize: '1rem' }}>{card.title}</h3>
                  <p style={{ fontSize: '0.875rem', color: 'var(--gray-600)', marginBottom: '0.875rem' }}>{card.desc}</p>
                  <p style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginBottom: '0.875rem' }}>
                    {t('sampleCases.estimatedTime')}: {card.eta}
                  </p>
                  <Link href={card.ctaHref} className="btn btn-primary btn-sm">
                    {card.ctaLabel}
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
