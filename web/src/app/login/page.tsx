'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useLanguage } from '@/lib/contexts';
import { devLogin, type BffRole } from '@/lib/bffClient';

// SkillSight Logo Component
const SkillSightLogo = ({ size = 48 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path 
      d="M16 6C8 6 2 16 2 16C2 16 8 26 16 26C24 26 30 16 30 16C30 16 24 6 16 6Z" 
      fill="url(#eyeGradientLogin)" 
      stroke="white" 
      strokeWidth="1.5"
    />
    <circle cx="16" cy="16" r="6" fill="white" opacity="0.9"/>
    <path 
      d="M12 19L14.5 16L16.5 17.5L20 13" 
      stroke="#E18182" 
      strokeWidth="2" 
      strokeLinecap="round" 
      strokeLinejoin="round"
    />
    <circle cx="13" cy="13" r="1.5" fill="white" opacity="0.8"/>
    <circle cx="20" cy="13" r="1.5" fill="#E18182"/>
    <defs>
      <linearGradient id="eyeGradientLogin" x1="2" y1="16" x2="30" y2="16" gradientUnits="userSpaceOnUse">
        <stop stopColor="#F9CE9C"/>
        <stop offset="0.5" stopColor="#E18182"/>
        <stop offset="1" stopColor="#C9DDE3"/>
      </linearGradient>
    </defs>
  </svg>
);

export default function LoginPage() {
  const router = useRouter();
  const { t } = useLanguage();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [role, setRole] = useState<'student' | 'admin'>('student');

  const [error, setError] = useState('');

  const doLogin = async (subjectId: string, displayName: string, emailAddr: string) => {
    setLoading(true);
    setError('');
    try {
      const bffRole: BffRole = role === 'admin' ? 'admin' : 'student';
      await devLogin({ subject_id: subjectId, role: bffRole, ttl_s: 86400 });
      localStorage.setItem('user', JSON.stringify({
        id: subjectId,
        name: displayName,
        email: emailAddr,
        role: bffRole,
        avatar: displayName[0].toUpperCase()
      }));
      router.push(role === 'admin' ? '/admin' : '/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
      setLoading(false);
    }
  };

  const handleHKULogin = () => {
    doLogin('hku_demo_user', 'Demo Student', 'demo@connect.hku.hk');
  };

  const handleEmailLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    const name = email.split('@')[0];
    doLogin(`email_${name}`, name, email);
  };

  return (
    <div className="login-page">
      <div className="login-card fade-in">
        <div className="login-logo">
          <SkillSightLogo size={48} />
        </div>
        <h1 className="login-title">SkillSight</h1>
        <p className="login-subtitle">{t('login.subtitle')}</p>

        {/* Role Selection */}
        <div className="tabs" style={{ marginBottom: '1.5rem' }}>
          <button
            className={`tab ${role === 'student' ? 'active' : ''}`}
            onClick={() => setRole('student')}
            style={{
              background: role === 'student' ? 'linear-gradient(135deg, #FCF0F0, white)' : 'transparent',
              border: role === 'student' ? '2px solid #E18182' : '2px solid transparent'
            }}
          >
            {t('login.student')}
          </button>
          <button
            className={`tab ${role === 'admin' ? 'active' : ''}`}
            onClick={() => setRole('admin')}
            style={{
              background: role === 'admin' ? 'linear-gradient(135deg, #FCF0F0, white)' : 'transparent',
              border: role === 'admin' ? '2px solid #E18182' : '2px solid transparent'
            }}
          >
            {t('login.adminStaff')}
          </button>
        </div>

        {/* HKU SSO Button */}
        <button
          className="btn btn-primary btn-lg"
          style={{ width: '100%' }}
          onClick={handleHKULogin}
          disabled={loading}
        >
          {loading ? (
            <>
              <span className="spinner" style={{ width: '1rem', height: '1rem', borderWidth: '2px' }}></span>
              {t('login.connecting')}
            </>
          ) : (
            <>{t('login.signInHKU')}</>
          )}
        </button>

        <div className="login-divider">{t('login.or')}</div>

        {/* Email Login */}
        <form onSubmit={handleEmailLogin}>
          <div className="form-group">
            <input
              type="email"
              className="input"
              placeholder={t('login.emailPlaceholder')}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{
                borderColor: '#E7E5E4',
                transition: 'all 0.2s ease'
              }}
              onFocus={(e) => {
                e.currentTarget.style.borderColor = '#E18182';
                e.currentTarget.style.boxShadow = '0 0 0 3px rgba(225, 129, 130, 0.1)';
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor = '#E7E5E4';
                e.currentTarget.style.boxShadow = 'none';
              }}
            />
          </div>
          <button
            type="submit"
            className="btn btn-secondary"
            style={{ width: '100%' }}
            disabled={loading || !email}
          >
            {t('login.continueEmail')}
          </button>
        </form>

        {error && <p style={{ color: '#E18182', fontSize: '0.875rem', marginTop: '0.5rem' }}>{error}</p>}
        <p className="login-help">
          {t('login.needHelp')} <a href="mailto:support@hku.hk" style={{ color: '#E18182' }}>{t('login.contactUs')}</a>
        </p>
      </div>
      
      {/* HKU 115 Anniversary Logo */}
      <div style={{
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        opacity: 0.9,
        zIndex: 50,
      }}>
        <img 
          src="/hku-115.svg" 
          alt="HKU 115th Anniversary"
          style={{
            maxWidth: '160px',
            height: 'auto',
            filter: 'drop-shadow(0 4px 8px rgba(0,0,0,0.1))'
          }}
        />
      </div>
    </div>
  );
}
