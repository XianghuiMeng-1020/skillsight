'use client';

import { useState, useRef, useEffect } from 'react';
import { useTheme, useLanguage, LANGUAGES, Language } from '@/lib/contexts';

export function ThemeToggle({ showLabel = true }: { showLabel?: boolean }) {
  const { theme, toggleTheme } = useTheme();
  const { t } = useLanguage();

  return (
    <button
      onClick={toggleTheme}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        padding: showLabel ? '0.75rem 1rem' : '0.5rem',
        background: 'var(--gray-100)',
        border: '1px solid var(--gray-200)',
        borderRadius: 'var(--radius)',
        cursor: 'pointer',
        transition: 'all 0.2s ease'
      }}
      title={theme === 'light' ? t('settings.dark') : t('settings.light')}
    >
      <div style={{
        width: '40px',
        height: '22px',
        borderRadius: '11px',
        background: theme === 'dark'
          ? 'linear-gradient(135deg, var(--coral), var(--peach))'
          : 'var(--gray-300)',
        position: 'relative',
        transition: 'background 0.3s ease'
      }}>
        <div style={{
          width: '18px',
          height: '18px',
          borderRadius: '50%',
          background: 'white',
          position: 'absolute',
          top: '2px',
          left: theme === 'dark' ? '20px' : '2px',
          transition: 'left 0.3s ease',
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '0.75rem'
        }}>
          {theme === 'dark' ? '🌙' : '☀️'}
        </div>
      </div>
      {showLabel && (
        <span style={{ fontSize: '0.875rem', color: 'var(--gray-700)' }}>
          {theme === 'light' ? t('settings.light') : t('settings.dark')}
        </span>
      )}
    </button>
  );
}

export function LanguageToggle({ showLabel = true }: { showLabel?: boolean }) {
  const { language, setLanguage } = useLanguage();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const current = LANGUAGES.find(l => l.value === language) ?? LANGUAGES[0];

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          padding: showLabel ? '0.75rem 1rem' : '0.5rem',
          background: 'var(--gray-100)',
          border: '1px solid var(--gray-200)',
          borderRadius: 'var(--radius)',
          cursor: 'pointer',
          transition: 'all 0.2s ease',
          minWidth: showLabel ? '130px' : 'auto',
        }}
        title={current.label}
      >
        <div style={{
          width: '28px',
          height: '28px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, var(--teal), var(--sage))',
          color: 'white',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '0.6rem',
          fontWeight: 700,
          flexShrink: 0,
        }}>
          {current.short}
        </div>
        {showLabel && (
          <span style={{ fontSize: '0.875rem', color: 'var(--gray-700)', flex: 1, textAlign: 'left' }}>
            {current.label}
          </span>
        )}
        {showLabel && (
          <span style={{ fontSize: '0.625rem', color: 'var(--gray-400)' }}>
            {open ? '▲' : '▼'}
          </span>
        )}
      </button>

      {open && (
        <div style={{
          position: 'absolute',
          top: 'calc(100% + 4px)',
          left: 0,
          right: 0,
          background: 'white',
          border: '1px solid var(--gray-200)',
          borderRadius: 'var(--radius)',
          boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
          zIndex: 1000,
          overflow: 'hidden',
          minWidth: '140px',
        }}>
          {LANGUAGES.map((lang) => (
            <button
              key={lang.value}
              onClick={() => { setLanguage(lang.value as Language); setOpen(false); }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.625rem',
                width: '100%',
                padding: '0.625rem 0.875rem',
                background: language === lang.value ? 'var(--gray-100)' : 'transparent',
                border: 'none',
                cursor: 'pointer',
                fontSize: '0.875rem',
                color: language === lang.value ? 'var(--sage-dark)' : 'var(--gray-700)',
                fontWeight: language === lang.value ? 600 : 400,
                textAlign: 'left',
                transition: 'background 0.15s ease',
              }}
              onMouseEnter={(e) => {
                if (language !== lang.value) e.currentTarget.style.background = 'var(--gray-50)';
              }}
              onMouseLeave={(e) => {
                if (language !== lang.value) e.currentTarget.style.background = 'transparent';
              }}
            >
              <div style={{
                width: '22px',
                height: '22px',
                borderRadius: '50%',
                background: language === lang.value
                  ? 'linear-gradient(135deg, var(--teal), var(--sage))'
                  : 'var(--gray-200)',
                color: language === lang.value ? 'white' : 'var(--gray-600)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '0.55rem',
                fontWeight: 700,
                flexShrink: 0,
              }}>
                {lang.short}
              </div>
              {lang.label}
              {language === lang.value && (
                <span style={{ marginLeft: 'auto', color: 'var(--sage-dark)' }}>✓</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
