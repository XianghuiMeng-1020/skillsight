'use client';

import { useTutorial, useLanguage } from '@/lib/contexts';

const tutorialSteps = [
  {
    icon: '👋',
    titleKey: 'tutorial.welcome',
    descKey: 'tutorial.step1',
    image: '📤',
  },
  {
    icon: '📝',
    titleKey: 'assess.title',
    descKey: 'tutorial.step2',
    image: '🎙️',
  },
  {
    icon: '📊',
    titleKey: 'dashboard.skills',
    descKey: 'tutorial.step3',
    image: '📈',
  },
  {
    icon: '🎯',
    titleKey: 'learning.path',
    descKey: 'tutorial.step4',
    image: '🚀',
  },
];

export function TutorialOverlay() {
  const { showTutorial, currentStep, totalSteps, nextStep, prevStep, skipTutorial, completeTutorial } = useTutorial();
  const { t } = useLanguage();

  if (!showTutorial) return null;

  const step = tutorialSteps[currentStep];
  const isLastStep = currentStep === totalSteps - 1;

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0, 0, 0, 0.7)',
      backdropFilter: 'blur(4px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 9999,
      animation: 'fadeIn 0.3s ease'
    }}>
      <div style={{
        background: 'var(--white)',
        borderRadius: 'var(--radius-xl)',
        padding: '2.5rem',
        maxWidth: '480px',
        width: '90%',
        boxShadow: 'var(--shadow-lg)',
        position: 'relative',
        animation: 'slideUp 0.3s ease'
      }}>
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
        <h2 style={{
          textAlign: 'center',
          marginBottom: '1rem',
          fontSize: '1.5rem',
          color: 'var(--gray-900)'
        }}>
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

        {/* Navigation */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <button
            onClick={skipTutorial}
            style={{
              padding: '0.625rem 1rem',
              background: 'transparent',
              border: 'none',
              color: 'var(--gray-500)',
              cursor: 'pointer',
              fontSize: '0.875rem'
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
              onClick={isLastStep ? completeTutorial : nextStep}
              className="btn btn-primary"
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
