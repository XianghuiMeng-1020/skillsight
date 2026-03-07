'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState, useCallback } from 'react';
import ApiStatus from './ApiStatus';
import { useLanguage } from '@/lib/contexts';
import { clearToken } from '@/lib/bffClient';

// SkillSight Logo - 代表技能洞察与成长的创意设计
// 融合了眼睛（洞察）+ 上升图表（成长）+ 技能连接点的概念
const SkillSightLogo = () => (
  <svg width="28" height="28" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    {/* 眼睛外形 - 代表洞察 */}
    <path 
      d="M16 6C8 6 2 16 2 16C2 16 8 26 16 26C24 26 30 16 30 16C30 16 24 6 16 6Z" 
      fill="url(#eyeGradient)" 
      stroke="white" 
      strokeWidth="1.5"
    />
    {/* 瞳孔 + 上升趋势图 */}
    <circle cx="16" cy="16" r="6" fill="white" opacity="0.9"/>
    {/* 技能成长曲线 */}
    <path 
      d="M12 19L14.5 16L16.5 17.5L20 13" 
      stroke="#E18182" 
      strokeWidth="2" 
      strokeLinecap="round" 
      strokeLinejoin="round"
    />
    {/* 洞察闪光点 */}
    <circle cx="13" cy="13" r="1.5" fill="white" opacity="0.8"/>
    {/* 技能节点装饰 */}
    <circle cx="20" cy="13" r="1.5" fill="#E18182"/>
    <defs>
      <linearGradient id="eyeGradient" x1="2" y1="16" x2="30" y2="16" gradientUnits="userSpaceOnUse">
        <stop stopColor="#F9CE9C"/>
        <stop offset="0.5" stopColor="#E18182"/>
        <stop offset="1" stopColor="#C9DDE3"/>
      </linearGradient>
    </defs>
  </svg>
);

interface User {
  id: string;
  name: string;
  email: string;
  role: 'student' | 'admin';
  avatar: string;
}

interface NavItem {
  icon: string;
  labelKey: string;
  hintKey?: string;
  href: string;
  roles?: ('student' | 'admin')[];
}

const studentNav: NavItem[] = [
  { icon: '🏠', labelKey: 'nav.dashboard', hintKey: 'nav.hint.dashboard', href: '/dashboard' },
  { icon: '📤', labelKey: 'dashboard.uploadEvidence', hintKey: 'nav.hint.upload', href: '/dashboard/upload' },
  { icon: '📊', labelKey: 'dashboard.skills', hintKey: 'nav.hint.skills', href: '/dashboard/skills' },
  { icon: '🎯', labelKey: 'dashboard.jobs', hintKey: 'nav.hint.jobs', href: '/dashboard/jobs' },
  { icon: '📝', labelKey: 'dashboard.assessments', hintKey: 'nav.hint.assessments', href: '/dashboard/assessments' },
  { icon: '📜', labelKey: 'changelog.navLabel', hintKey: 'nav.hint.changeLog', href: '/dashboard/change-log' },
];

const adminNav: NavItem[] = [
  { icon: '🏠', labelKey: 'admin.overview', href: '/admin' },
  { icon: '👥', labelKey: 'admin.audit', href: '/admin/audit' },
  { icon: '📋', labelKey: 'admin.jobs', href: '/admin/jobs' },
  { icon: '📜', labelKey: 'admin.changeLog', href: '/admin/change-log' },
  { icon: '🎯', labelKey: 'admin.skillsRegistry', href: '/admin/skills' },
  { icon: '💼', labelKey: 'admin.rolesLibrary', href: '/admin/roles' },
  { icon: '📚', labelKey: 'admin.courses', href: '/admin/course-skill-map' },
  { icon: '📈', labelKey: 'admin.analytics', href: '/admin/metrics' },
];

const settingsNav: NavItem[] = [
  { icon: '⚙️', labelKey: 'nav.settings', hintKey: 'nav.hint.settings', href: '/settings' },
  { icon: '🔒', labelKey: 'nav.privacy', hintKey: 'nav.hint.privacy', href: '/settings/privacy' },
];

export default function Sidebar() {
  const { t } = useLanguage();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const userData = localStorage.getItem('user');
    if (userData) {
      setUser(JSON.parse(userData));
    }
  }, []);

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    setIsMobile(mq.matches);
    const handler = () => setIsMobile(mq.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const closeMobile = useCallback(() => setMobileOpen(false), []);

  useEffect(() => {
    if (isMobile) setMobileOpen(false);
  }, [pathname, isMobile]);

  const isAdmin = user?.role === 'admin';
  const navItems = isAdmin ? adminNav : studentNav;

  const handleLogout = () => {
    localStorage.removeItem('user');
    clearToken();
    window.location.href = '/login';
  };

  return (
    <>
      {isMobile && (
        <button
          type="button"
          className="sidebar-hamburger"
          onClick={() => setMobileOpen(true)}
          aria-label={t('nav.openMenu')}
        >
          <span className="sidebar-hamburger-bar" />
          <span className="sidebar-hamburger-bar" />
          <span className="sidebar-hamburger-bar" />
        </button>
      )}
      {isMobile && mobileOpen && (
        <div className="sidebar-backdrop" onClick={closeMobile} aria-hidden />
      )}
      <aside className={`sidebar ${mobileOpen && isMobile ? 'open' : ''}`}>
      <div className="sidebar-header">
        {isMobile && (
          <button type="button" className="sidebar-close" onClick={closeMobile} aria-label={t('nav.closeMenu')}>
            ✕
          </button>
        )}
        <Link href={isAdmin ? '/admin' : '/dashboard'} className="sidebar-logo" onClick={isMobile ? closeMobile : undefined}>
          <div className="sidebar-logo-icon">
            <SkillSightLogo />
          </div>
          <span>SkillSight</span>
        </Link>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section">
          <div className="nav-section-title">
            {isAdmin ? t('admin.administration') : t('nav.mainMenu')}
          </div>
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`nav-item ${pathname === item.href ? 'active' : ''}`}
              title={item.hintKey ? t(item.hintKey) : ''}
              onClick={isMobile ? closeMobile : undefined}
            >
              <span className="nav-item-icon">{item.icon}</span>
              <span>{t(item.labelKey)}</span>
            </Link>
          ))}
        </div>

        <div className="nav-section">
          <div className="nav-section-title">{t('nav.settings')}</div>
          {settingsNav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`nav-item ${pathname === item.href ? 'active' : ''}`}
              title={item.hintKey ? t(item.hintKey) : ''}
              onClick={isMobile ? closeMobile : undefined}
            >
              <span className="nav-item-icon">{item.icon}</span>
              <span>{t(item.labelKey)}</span>
            </Link>
          ))}
        </div>
      </nav>

      <div className="sidebar-footer">
        <div style={{ marginBottom: '0.75rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--gray-100)' }}>
          <ApiStatus />
        </div>
        <div className="user-info">
          <div className="user-avatar">{user?.avatar || 'U'}</div>
          <div className="user-details">
            <div className="user-name">{user?.name || t('common.loading')}</div>
            <div className="user-role">{isAdmin ? t('user.administrator') : t('user.student')}</div>
          </div>
          <button 
            className="btn btn-icon btn-ghost" 
            onClick={handleLogout}
            title={t('action.signOut')}
          >
            🚪
          </button>
        </div>
      </div>
    </aside>
    </>
  );
}
