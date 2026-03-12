'use client';

import { useMemo, useState, useEffect, useCallback } from 'react';
import { useTutorial, useLanguage } from '@/lib/contexts';

export function TutorialOverlay() {
  const {
    showTutorial,
    currentStep,
    totalSteps,
    tutorialName,
    setTutorialName,
    nextStep,
    prevStep,
    skipTutorial,
    completeTutorial,
  } = useTutorial();
  const { t, language, setLanguage } = useLanguage();
  const [localName, setLocalName] = useState(tutorialName);

  useEffect(() => {
    if (!showTutorial) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        skipTutorial();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [showTutorial, skipTutorial]);

  const tutorialSteps = useMemo(
    () => [
      {
        icon: '👋',
        titleKey: 'tutorial.helloTitle',
        descKey: 'tutorial.helloDesc',
        image: '✨',
      },
      {
        icon: '📤',
        titleKey: 'tutorial.uploadTitle',
        descKey: 'tutorial.uploadDesc',
        image: '📁',
      },
      {
        icon: '📝',
        titleKey: 'tutorial.assessTitle',
        descKey: 'tutorial.assessDesc',
        image: '🎙️',
      },
      {
        icon: '📊',
        titleKey: 'tutorial.profileTitle',
        descKey: 'tutorial.profileDesc',
        image: '📈',
      },
      {
        icon: '🧭',
        titleKey: 'tutorial.routeTitle',
        descKey: 'tutorial.routeDesc',
        image: '🚀',
      },
    ],
    []
  );

  if (!showTutorial) return null;

  const step = tutorialSteps[currentStep];
  const isLastStep = currentStep === totalSteps - 1;
  const canContinue = currentStep === 0 ? localName.trim().length > 0 : true;

  const applyName = () => {
    const trimmed = localName.trim();
    if (!trimmed) return;
    setTutorialName(trimmed);
    try {
      const rawUser = localStorage.getItem('user');
      if (!rawUser) return;
      const parsed = JSON.parse(rawUser) as Record<string, string>;
      parsed.name = trimmed;
      parsed.avatar = trimmed.charAt(0).toUpperCase();
      localStorage.setItem('user', JSON.stringify(parsed));
    } catch {
      // keep onboarding flow resilient even if local profile cannot be parsed
    }
  };

  const handleNext = () => {
    if (currentStep === 0) applyName();
    if (isLastStep) {
      completeTutorial();
      return;
    }
    nextStep();
  };

  const handleOverlayClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) skipTutorial();
    },
    [skipTutorial]
  );

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="tutorial-title"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.7)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        animation: 'fadeIn 0.3s ease',
      }}
      onClick={handleOverlayClick}
    >
      <div
        style={{
          background: 'var(--white)',
          borderRadius: 'var(--radius-xl)',
          maxWidth: '480px',
          width: '90%',
          maxHeight: 'calc(100vh - 2rem)',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: 'var(--shadow-lg)',
          position: 'relative',
          animation: 'slideUp 0.3s ease',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close × button */}
        <button
          type="button"
          onClick={skipTutorial}
          aria-label={t('tutorial.skip')}
          style={{
            position: 'absolute',
            top: '1rem',
            right: '1rem',
            width: '32px',
            height: '32px',
            borderRadius: '50%',
            border: 'none',
            background: 'var(--gray-100)',
            color: 'var(--gray-600)',
            fontSize: '1.25rem',
            lineHeight: 1,
            cursor: 'pointer',
            zIndex: 1,
          }}
        >
          ×
        </button>

        {/* Scrollable content */}
        <div style={{ padding: '2.5rem 2.5rem 0', overflowY: 'auto', flex: '1 1 auto', minHeight: 0 }}>
        {/* Progress Dots */}
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          gap: '0.5rem',
          marginBottom: '2rem'
        }}>
          {Array.from({ length: totalSteps }).map((_, i) => (
            <div
              key={i}
              style={{
                width: i === currentStep ? '24px' : '8px',
                height: '8px',
                borderRadius: '4px',
                background: i === currentStep 
                  ? 'linear-gradient(135deg, var(--coral), var(--peach))'
                  : i < currentStep 
                    ? 'var(--sage)' 
                    : 'var(--gray-200)',
                transition: 'all 0.3s ease'
              }}
            />
          ))}
        </div>

        {/* Icon */}
        <div style={{
          width: '100px',
          height: '100px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, var(--peach-light), var(--coral-light))',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '3rem',
          margin: '0 auto 1.5rem',
          boxShadow: '0 8px 24px -8px rgba(225, 129, 130, 0.3)'
        }}>
          {step.image}
        </div>

        {/* Content */}
        <h2
          id="tutorial-title"
          style={{
            textAlign: 'center',
            marginBottom: '1rem',
            fontSize: '1.5rem',
            color: 'var(--gray-900)',
          }}
        >
          {step.icon} {t(step.titleKey)}
        </h2>

        <p style={{
          textAlign: 'center',
          color: 'var(--gray-600)',
          marginBottom: '2rem',
          lineHeight: 1.6
        }}>
          {t(step.descKey)}
        </p>

        {currentStep === 0 && (
          <div style={{ marginBottom: '1.25rem' }}>
            <label style={{ display: 'block', fontSize: '0.813rem', color: 'var(--gray-600)', marginBottom: '0.375rem' }}>
              {t('tutorial.nameLabel')}
            </label>
            <input
              value={localName}
              onChange={(e) => setLocalName(e.target.value)}
              placeholder={t('tutorial.namePlaceholder')}
              maxLength={40}
              style={{
                width: '100%',
                border: '1px solid var(--gray-300)',
                borderRadius: '10px',
                padding: '0.625rem 0.75rem',
                fontSize: '0.95rem',
                marginBottom: '0.75rem',
              }}
            />
            <label style={{ display: 'block', fontSize: '0.813rem', color: 'var(--gray-600)', marginBottom: '0.375rem' }}>
              {t('tutorial.languageLabel')}
            </label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              {[
                { code: 'zh', label: '简中' },
                { code: 'zh-TW', label: '繁中' },
                { code: 'en', label: 'EN' },
              ].map((item) => (
                <button
                  key={item.code}
                  onClick={() => setLanguage(item.code as 'zh' | 'zh-TW' | 'en')}
                  className="btn btn-sm"
                  style={{
                    border: '1px solid var(--gray-200)',
                    background: language === item.code ? 'var(--coral-light)' : 'var(--white)',
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {currentStep === totalSteps - 1 && (
          <div style={{
            background: 'var(--gray-50)',
            borderRadius: '10px',
            padding: '0.75rem',
            marginBottom: '1.25rem',
            fontSize: '0.875rem',
            color: 'var(--gray-700)',
            lineHeight: 1.5,
          }}>
            {t('tutorial.routeFlow')}
          </div>
        )}
        </div>

        {/* Sticky footer: always visible (Skip / Prev / Next) */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '1rem 2.5rem 2.5rem',
            flexShrink: 0,
            borderTop: '1px solid var(--gray-100)',
            background: 'var(--white)',
            borderRadius: '0 0 var(--radius-xl) var(--radius-xl)',
          }}
        >
          <button
            onClick={skipTutorial}
            style={{
              padding: '0.625rem 1rem',
              background: 'transparent',
              border: 'none',
              color: 'var(--gray-500)',
              cursor: 'pointer',
              fontSize: '0.875rem',
            }}
          >
            {t('tutorial.skip')}
          </button>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            {currentStep > 0 && (
              <button
                onClick={prevStep}
                className="btn btn-secondary"
              >
                {t('tutorial.prev')}
              </button>
            )}
            <button
              onClick={handleNext}
              className="btn btn-primary"
              disabled={!canContinue}
            >
              {isLastStep ? t('tutorial.finish') : t('tutorial.next')}
            </button>
          </div>
        </div>
      </div>

      <style jsx>{`
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
