'use client';

import { useState, useRef, useCallback } from 'react';
import { useLanguage, getDateLocale } from '@/lib/contexts';
import { logger } from '@/lib/logger';

interface ShareButtonProps {
  userName: string;
  skills: { name: string; level: number }[];
  overallScore: number;
}

export function ShareButton({ userName, skills, overallScore }: ShareButtonProps) {
  const { t } = useLanguage();
  const [showModal, setShowModal] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleShare = () => {
    setShowModal(true);
  };

  const handleCopyLink = async () => {
    const shareUrl = window.location.origin + '/dashboard';
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      logger.error('Failed to copy', err);
    }
  };

  const handleNativeShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({
          title: `${userName}${t('share.profileOf')}`,
          text: t('share.nativeShareText').replace('{{name}}', userName).replace('{{score}}', String(overallScore)),
          url: window.location.origin + '/dashboard',
        });
      } catch (err) {
        logger.error('Share failed', err);
      }
    }
  };

  return (
    <>
      <button
        onClick={handleShare}
        style={{
          padding: '0.625rem 1rem',
          borderRadius: '10px',
          border: '2px solid #E7E5E4',
          background: 'white',
          color: '#44403C',
          fontWeight: 500,
          fontSize: '0.875rem',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          transition: 'all 0.2s ease',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = 'var(--sage)';
          e.currentTarget.style.background = 'var(--sage-50)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = '#E7E5E4';
          e.currentTarget.style.background = 'white';
        }}
      >
        📤 {t('share.button')}
      </button>

      {/* 分享模态框 */}
      {showModal && (
        <ShareModal
          userName={userName}
          skills={skills}
          overallScore={overallScore}
          onClose={() => setShowModal(false)}
          onCopyLink={handleCopyLink}
          onNativeShare={handleNativeShare}
          copied={copied}
        />
      )}
    </>
  );
}

interface ShareModalProps {
  userName: string;
  skills: { name: string; level: number }[];
  overallScore: number;
  onClose: () => void;
  onCopyLink: () => void;
  onNativeShare: () => void;
  copied: boolean;
}

function ShareModal({
  userName,
  skills,
  overallScore,
  onClose,
  onCopyLink,
  onNativeShare,
  copied,
}: ShareModalProps) {
  const { t, language } = useLanguage();
  const locale = getDateLocale(language);
  const cardRef = useRef<HTMLDivElement>(null);

  const handleDownloadImage = useCallback(async () => {
    if (!cardRef.current) return;

    try {
      const { toPng } = await import('html-to-image');
      const dataUrl = await toPng(cardRef.current, {
        backgroundColor: '#ffffff',
        pixelRatio: 2,
      });

      const link = document.createElement('a');
      link.download = `${userName}-skillsight-profile.png`;
      link.href = dataUrl;
      link.click();
    } catch (err) {
      logger.error('Failed to generate image', err);
      alert(t('share.noHtml2canvas'));
    }
  }, [userName]);

  const topSkills = skills.slice(0, 4);

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: '1rem',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'white',
          borderRadius: '20px',
          maxWidth: '480px',
          width: '100%',
          maxHeight: '90vh',
          overflow: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div
          style={{
            padding: '1.25rem 1.5rem',
            borderBottom: '1px solid var(--gray-100)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <h3 style={{ fontWeight: 600, fontSize: '1.125rem' }}>{t('share.shareProfile')}</h3>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              fontSize: '1.5rem',
              cursor: 'pointer',
              color: 'var(--gray-400)',
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>

        {/* 预览卡片 */}
        <div style={{ padding: '1.5rem' }}>
          <div
            ref={cardRef}
            style={{
              background: 'linear-gradient(135deg, #98B8A8 0%, #C9DDE3 50%, #F9CE9C 100%)',
              borderRadius: '16px',
              padding: '1.5rem',
              color: 'white',
            }}
          >
            {/* Logo */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                marginBottom: '1.5rem',
              }}
            >
              <span style={{ fontSize: '1.25rem' }}>🎓</span>
              <span style={{ fontWeight: 700, fontSize: '1rem' }}>SkillSight</span>
            </div>

            {/* 用户信息 */}
            <div style={{ marginBottom: '1.5rem' }}>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.25rem' }}>
                {userName}
              </div>
              <div style={{ opacity: 0.8, fontSize: '0.875rem' }}>{t('share.skillProfile')}</div>
            </div>

            {/* 综合得分 */}
            <div
              style={{
                background: 'rgba(255, 255, 255, 0.2)',
                backdropFilter: 'blur(10px)',
                borderRadius: '12px',
                padding: '1rem',
                marginBottom: '1rem',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: '0.75rem', opacity: 0.8, marginBottom: '0.25rem' }}>
                {t('share.overallScore')}
              </div>
              <div style={{ fontSize: '2.5rem', fontWeight: 800 }}>{overallScore}%</div>
            </div>

            {/* 技能列表 */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '0.5rem',
              }}
            >
              {topSkills.map((skill) => (
                <div
                  key={skill.name}
                  style={{
                    background: 'rgba(255, 255, 255, 0.15)',
                    borderRadius: '8px',
                    padding: '0.625rem 0.75rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    fontSize: '0.8125rem',
                  }}
                >
                  <span
                    style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {skill.name}
                  </span>
                  <span style={{ fontWeight: 700 }}>Lv.{skill.level}</span>
                </div>
              ))}
            </div>

            {/* 底部 */}
            <div
              style={{
                marginTop: '1.5rem',
                paddingTop: '1rem',
                borderTop: '1px solid rgba(255, 255, 255, 0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '0.75rem',
                opacity: 0.7,
              }}
            >
              <span>skillsight.hku.hk</span>
              <span>{new Date().toLocaleDateString(locale)}</span>
            </div>
          </div>
        </div>

        {/* 分享选项 */}
        <div
          style={{
            padding: '0 1.5rem 1.5rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem',
          }}
        >
          <button
            onClick={onCopyLink}
            style={{
              width: '100%',
              padding: '0.875rem',
              borderRadius: '10px',
              border: '1px solid var(--gray-200)',
              background: copied ? 'var(--sage-50)' : 'white',
              color: copied ? 'var(--sage-dark)' : 'var(--gray-900)',
              fontWeight: 500,
              fontSize: '0.9375rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
              transition: 'all 0.2s ease',
            }}
          >
            {copied ? (
              <>✓ 已复制链接</>
            ) : (
              <>🔗 复制分享链接</>
            )}
          </button>

          <button
            onClick={handleDownloadImage}
            style={{
              width: '100%',
              padding: '0.875rem',
              borderRadius: '10px',
              border: '1px solid var(--gray-200)',
              background: 'white',
              color: 'var(--gray-900)',
              fontWeight: 500,
              fontSize: '0.9375rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
            }}
          >
            📷 下载为图片
          </button>

          {typeof navigator !== 'undefined' && 'share' in navigator && (
            <button
              onClick={onNativeShare}
              style={{
                width: '100%',
                padding: '0.875rem',
                borderRadius: '10px',
                border: 'none',
                background: 'linear-gradient(135deg, var(--sage), var(--sage-dark))',
                color: 'white',
                fontWeight: 600,
                fontSize: '0.9375rem',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.5rem',
              }}
            >
              📤 更多分享选项
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// 简单的分享图标按钮
interface ShareIconButtonProps {
  onClick?: () => void;
  size?: 'sm' | 'md' | 'lg';
}

export function ShareIconButton({ onClick, size = 'md' }: ShareIconButtonProps) {
  const sizes = {
    sm: { width: '32px', height: '32px', fontSize: '0.875rem' },
    md: { width: '40px', height: '40px', fontSize: '1rem' },
    lg: { width: '48px', height: '48px', fontSize: '1.25rem' },
  };

  const sizeStyle = sizes[size];

  return (
    <button
      onClick={onClick}
      style={{
        ...sizeStyle,
        borderRadius: '10px',
        border: '1px solid var(--gray-200)',
        background: 'white',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transition: 'all 0.2s ease',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = 'var(--gray-50)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'white';
      }}
      title="分享"
    >
      📤
    </button>
  );
}
