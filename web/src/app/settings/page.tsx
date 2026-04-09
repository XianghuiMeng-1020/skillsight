'use client';

import { useEffect, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { LanguageToggle, ThemeToggle } from '@/components/ThemeToggle';
import { useLanguage } from '@/lib/contexts';
import { clearToken } from '@/lib/bffClient';

const NOTIFICATION_PREFS_KEY = 'skillsight_notifications';

interface User {
  id: string;
  name: string;
  email: string;
  role: 'student' | 'admin';
}

export default function SettingsPage() {
  const { t } = useLanguage();
  const [user, setUser] = useState<User | null>(null);
  const [notifications, setNotifications] = useState({
    email: true,
    skillUpdates: true,
    reviewComplete: true,
    weeklyDigest: false,
  });

  useEffect(() => {
    try {
      const userData = localStorage.getItem('user');
      if (userData) {
        setUser(JSON.parse(userData));
      }
    } catch (e) {
      console.warn('Failed to read user from localStorage:', e);
    }
    // Load notification preferences from localStorage
    try {
      const notifData = localStorage.getItem(NOTIFICATION_PREFS_KEY);
      if (notifData) {
        setNotifications(prev => ({ ...prev, ...JSON.parse(notifData) }));
      }
    } catch (e) {
      console.warn('Failed to read notifications from localStorage:', e);
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(NOTIFICATION_PREFS_KEY, JSON.stringify(notifications));
    } catch (e) {
      console.warn('Failed to save notifications to localStorage:', e);
    }
  }, [notifications]);

  const handleNotificationChange = (key: string) => {
    setNotifications(prev => ({ ...prev, [key]: !prev[key as keyof typeof prev] }));
  };

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">{t('settings.pageTitle')}</h1>
            <p className="page-subtitle">{t('settings.pageSubtitle')}</p>
          </div>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <LanguageToggle />
            <ThemeToggle />
          </div>
        </div>

        <div className="page-content">
          {/* Profile Section */}
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <div className="card-header">
              <h3 className="card-title">{t('settings.profile')}</h3>
            </div>
            <div className="card-content">
              <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', marginBottom: '1.5rem' }}>
                <div style={{
                  width: '80px',
                  height: '80px',
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, var(--primary), var(--primary-light))',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'white',
                  fontSize: '2rem',
                  fontWeight: 600
                }}>
                  {user?.name?.[0]?.toUpperCase() || 'U'}
                </div>
                <div>
                  <h3 style={{ marginBottom: '0.25rem' }}>{user?.name || t('common.loading')}</h3>
                  <p style={{ color: 'var(--gray-500)' }}>{user?.email}</p>
                  <span className="badge badge-primary" style={{ marginTop: '0.5rem' }}>
                    {user?.role === 'admin' ? `👩‍💼 ${t('settings.administrator')}` : t('login.student')}
                  </span>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="form-group">
                  <label className="label">{t('settings.displayName')}</label>
                  <input 
                    type="text" 
                    className="input" 
                    value={user?.name || ''} 
                    onChange={(e) => setUser(prev => prev ? {...prev, name: e.target.value} : null)}
                  />
                </div>
                <div className="form-group">
                  <label className="label">{t('settings.email')}</label>
                  <input type="email" className="input" value={user?.email || ''} disabled />
                </div>
              </div>

              <button
                className="btn btn-primary"
                onClick={() => {
                  if (user) {
                    try {
                      localStorage.setItem('user', JSON.stringify(user));
                    } catch (e) {
                      console.warn('Failed to save user to localStorage:', e);
                    }
                  }
                }}
              >
                {t('settings.saveChanges')}
              </button>
            </div>
          </div>

          {/* Notifications */}
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <div className="card-header">
              <h3 className="card-title">{t('settings.notifications')}</h3>
            </div>
            <div className="card-content">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {[
                  { key: 'email', labelKey: 'settings.emailNotif', descKey: 'settings.emailNotifDesc' },
                  { key: 'skillUpdates', labelKey: 'settings.skillUpdates', descKey: 'settings.skillUpdatesDesc' },
                  { key: 'reviewComplete', labelKey: 'settings.reviewComplete', descKey: 'settings.reviewCompleteDesc' },
                  { key: 'weeklyDigest', labelKey: 'settings.weeklyDigest', descKey: 'settings.weeklyDigestDesc' },
                ].map((item) => (
                  <div 
                    key={item.key}
                    style={{ 
                      display: 'flex', 
                      justifyContent: 'space-between', 
                      alignItems: 'center',
                      padding: '1rem',
                      background: 'var(--gray-50)',
                      borderRadius: 'var(--radius)'
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 500 }}>{t(item.labelKey)}</div>
                      <div style={{ fontSize: '0.813rem', color: 'var(--gray-500)' }}>{t(item.descKey)}</div>
                    </div>
                    <label style={{ position: 'relative', display: 'inline-block', width: '48px', height: '24px' }}>
                      <input 
                        type="checkbox" 
                        checked={notifications[item.key as keyof typeof notifications]}
                        onChange={() => handleNotificationChange(item.key)}
                        style={{ opacity: 0, width: 0, height: 0 }}
                      />
                      <span style={{
                        position: 'absolute',
                        cursor: 'pointer',
                        top: 0, left: 0, right: 0, bottom: 0,
                        background: notifications[item.key as keyof typeof notifications] ? 'var(--primary)' : 'var(--gray-300)',
                        borderRadius: '24px',
                        transition: '0.3s'
                      }}>
                        <span style={{
                          position: 'absolute',
                          content: '',
                          height: '18px',
                          width: '18px',
                          left: notifications[item.key as keyof typeof notifications] ? '27px' : '3px',
                          bottom: '3px',
                          background: 'white',
                          borderRadius: '50%',
                          transition: '0.3s'
                        }}></span>
                      </span>
                    </label>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Quick Links */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">{t('settings.quickLinks')}</h3>
            </div>
            <div className="card-content">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem' }}>
                <a 
                  href="/settings/privacy" 
                  style={{ 
                    padding: '1rem', 
                    background: 'var(--gray-50)', 
                    borderRadius: 'var(--radius)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    textDecoration: 'none',
                    color: 'inherit'
                  }}
                >
                  <span style={{ fontSize: '1.5rem' }}>🔒</span>
                  <div>
                    <div style={{ fontWeight: 500 }}>{t('settings.privacyData')}</div>
                    <div style={{ fontSize: '0.813rem', color: 'var(--gray-500)' }}>{t('settings.privacyDataDesc')}</div>
                  </div>
                </a>
                <a 
                  href="/dashboard/skills" 
                  style={{ 
                    padding: '1rem', 
                    background: 'var(--gray-50)', 
                    borderRadius: 'var(--radius)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    textDecoration: 'none',
                    color: 'inherit'
                  }}
                >
                  <span style={{ fontSize: '1.5rem' }}>📊</span>
                  <div>
                    <div style={{ fontWeight: 500 }}>{t('dashboard.skills')}</div>
                    <div style={{ fontSize: '0.813rem', color: 'var(--gray-500)' }}>{t('settings.viewSkillProfile')}</div>
                  </div>
                </a>
              </div>
            </div>
          </div>

          {/* Sign Out */}
          <div style={{ marginTop: '2rem', textAlign: 'center' }}>
            <button
              className="btn btn-secondary"
              onClick={() => {
                try {
                  localStorage.removeItem('user');
                } catch (e) {
                  console.warn('Failed to remove user from localStorage:', e);
                }
                clearToken();
                window.location.href = '/login';
              }}
            >
              {t('settings.signOut')}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
