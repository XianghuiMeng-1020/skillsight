'use client';

import { useAchievements, Achievement } from '@/lib/hooks';
import { useLanguage, getDateLocale } from '@/lib/contexts';
import { fmt2 } from '@/lib/formatNumber';

const rarityStyleMap: Record<Achievement['rarity'], { bg: string; border: string; text: string; glow: string }> = {
  common: {
    bg: 'linear-gradient(135deg, #f5f5f4, #e7e5e4)',
    border: '#d6d3d1',
    text: '#57534e',
    glow: 'none',
  },
  rare: {
    bg: 'linear-gradient(135deg, #dbeafe, #bfdbfe)',
    border: '#93c5fd',
    text: '#1d4ed8',
    glow: '0 0 12px rgba(59, 130, 246, 0.3)',
  },
  epic: {
    bg: 'linear-gradient(135deg, #f3e8ff, #e9d5ff)',
    border: '#c084fc',
    text: '#7c3aed',
    glow: '0 0 16px rgba(139, 92, 246, 0.4)',
  },
  legendary: {
    bg: 'linear-gradient(135deg, #fef3c7, #fde68a)',
    border: '#fbbf24',
    text: '#b45309',
    glow: '0 0 20px rgba(251, 191, 36, 0.5)',
  },
};

const rarityLabelKeys: Record<Achievement['rarity'], string> = {
  common: 'achievements.common',
  rare: 'achievements.rare',
  epic: 'achievements.epic',
  legendary: 'achievements.legendary',
};

// 分类图标
const categoryIcons: Record<Achievement['category'], string> = {
  assessment: '📝',
  learning: '📚',
  milestone: '🏅',
  special: '✨',
};

// 单个成就卡片
interface AchievementCardProps {
  achievement: Achievement;
  compact?: boolean;
}

export function AchievementCard({ achievement, compact = false }: AchievementCardProps) {
  const { t, language } = useLanguage();
  const style = rarityStyleMap[achievement.rarity];
  const progress = Math.min((achievement.progress / achievement.target) * 100, 100);
  const locale = getDateLocale(language);

  // Get localized name and description based on current language
  const getLocalizedName = () => {
    if (language === 'en') return achievement.nameEn;
    if (language === 'zh-TW') return achievement.nameZhTW;
    return achievement.name; // zh (simplified)
  };

  const getLocalizedDescription = () => {
    if (language === 'en') return achievement.descriptionEn;
    if (language === 'zh-TW') return achievement.descriptionZhTW;
    return achievement.description; // zh (simplified)
  };

  if (compact) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          padding: '0.75rem 1rem',
          background: achievement.unlocked ? style.bg : '#fafaf9',
          borderRadius: '12px',
          border: `1px solid ${achievement.unlocked ? style.border : '#e7e5e4'}`,
          opacity: achievement.unlocked ? 1 : 0.6,
          boxShadow: achievement.unlocked ? style.glow : 'none',
        }}
      >
        <span style={{ fontSize: '1.5rem', filter: achievement.unlocked ? 'none' : 'grayscale(1)' }}>
          {achievement.icon}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: '0.875rem', color: achievement.unlocked ? style.text : '#78716c' }}>
            {getLocalizedName()}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#a8a29e' }}>
            {achievement.unlocked ? t('achievements.unlocked') : `${fmt2(Math.round(progress))}%`}
          </div>
        </div>
        {achievement.unlocked && (
          <span
            style={{
              fontSize: '0.625rem',
              fontWeight: 600,
              padding: '0.125rem 0.375rem',
              borderRadius: '4px',
              background: style.bg,
              color: style.text,
              border: `1px solid ${style.border}`,
            }}
          >
            {t(rarityLabelKeys[achievement.rarity])}
          </span>
        )}
      </div>
    );
  }

  return (
    <div
      style={{
        padding: '1.25rem',
        background: achievement.unlocked ? style.bg : '#fafaf9',
        borderRadius: '16px',
        border: `2px solid ${achievement.unlocked ? style.border : '#e7e5e4'}`,
        opacity: achievement.unlocked ? 1 : 0.7,
        boxShadow: achievement.unlocked ? style.glow : 'none',
        transition: 'all 0.3s ease',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem', marginBottom: '1rem' }}>
        <div
          style={{
            width: '56px',
            height: '56px',
            borderRadius: '14px',
            background: achievement.unlocked ? 'white' : '#f5f5f4',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '2rem',
            filter: achievement.unlocked ? 'none' : 'grayscale(1)',
            boxShadow: achievement.unlocked ? '0 2px 8px rgba(0,0,0,0.08)' : 'none',
          }}
        >
          {achievement.icon}
        </div>
        <div style={{ flex: 1 }}>
          <div
            style={{
              fontWeight: 700,
              fontSize: '1rem',
              color: achievement.unlocked ? style.text : '#78716c',
              marginBottom: '0.25rem',
            }}
          >
            {getLocalizedName()}
          </div>
          <div style={{ fontSize: '0.813rem', color: '#78716c', lineHeight: 1.4 }}>
            {getLocalizedDescription()}
          </div>
        </div>
        <span
          style={{
            fontSize: '0.6875rem',
            fontWeight: 600,
            padding: '0.25rem 0.5rem',
            borderRadius: '6px',
            background: achievement.unlocked ? 'white' : '#f5f5f4',
            color: achievement.unlocked ? style.text : '#a8a29e',
            border: `1px solid ${achievement.unlocked ? style.border : '#e7e5e4'}`,
          }}
        >
          {t(rarityLabelKeys[achievement.rarity])}
        </span>
      </div>

      {!achievement.unlocked && (
        <div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              fontSize: '0.75rem',
              color: '#78716c',
              marginBottom: '0.5rem',
            }}
          >
            <span>{t('achievements.progress')}</span>
            <span>
              {achievement.progress} / {achievement.target}
            </span>
          </div>
          <div
            style={{
              height: '6px',
              background: '#e7e5e4',
              borderRadius: '3px',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                height: '100%',
                width: `${progress}%`,
                background: 'linear-gradient(90deg, #98B8A8, #BBCFC3)',
                borderRadius: '3px',
                transition: 'width 0.3s ease',
              }}
            />
          </div>
        </div>
      )}

      {achievement.unlocked && achievement.unlockedAt && (
        <div style={{ fontSize: '0.75rem', color: '#a8a29e', marginTop: '0.5rem' }}>
          {t('achievements.unlockedAt')} {new Date(achievement.unlockedAt).toLocaleDateString(locale)}
        </div>
      )}
    </div>
  );
}

const categoryLabelKeys: Record<Achievement['category'], string> = {
  assessment: 'achievements.assessmentTab',
  learning: 'achievements.learningTab',
  milestone: 'achievements.milestonesTab',
  special: 'achievements.specialTab',
};

export function AchievementsPanel() {
  const { t } = useLanguage();
  const { achievements, totalPoints } = useAchievements();

  const unlockedCount = achievements.filter((a) => a.unlocked).length;
  const categories = ['assessment', 'learning', 'milestone', 'special'] as const;

  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span
            style={{
              width: '28px',
              height: '28px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #fef3c7, #fde68a)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '0.875rem',
            }}
          >
            🏆
          </span>
          {t('achievements.system')}
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <span style={{ fontSize: '0.875rem', color: '#78716c' }}>
            {fmt2(unlockedCount)} / {fmt2(achievements.length)} {t('achievements.unlocked')}
          </span>
          <span
            style={{
              fontWeight: 700,
              color: '#b45309',
              background: 'linear-gradient(135deg, #fef3c7, #fde68a)',
              padding: '0.375rem 0.75rem',
              borderRadius: '8px',
              fontSize: '0.875rem',
            }}
          >
            {fmt2(totalPoints)} {t('achievements.points')}
          </span>
        </div>
      </div>

      <div className="card-content">
        {categories.map((category) => {
          const categoryAchievements = achievements.filter((a) => a.category === category);
          if (categoryAchievements.length === 0) return null;

          return (
            <div key={category} style={{ marginBottom: '1.5rem' }}>
              <h4
                style={{
                  fontSize: '0.875rem',
                  fontWeight: 600,
                  color: '#57534e',
                  marginBottom: '0.75rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                {categoryIcons[category]}
                {t(categoryLabelKeys[category])}
              </h4>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                  gap: '1rem',
                }}
              >
                {categoryAchievements.map((achievement) => (
                  <AchievementCard key={achievement.id} achievement={achievement} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// 成就解锁通知
interface AchievementNotificationProps {
  achievement: Achievement | null;
  onDismiss: () => void;
}

export function AchievementNotification({ achievement, onDismiss }: AchievementNotificationProps) {
  const { t, language } = useLanguage();
  if (!achievement) return null;

  const style = rarityStyleMap[achievement.rarity];

  // Get localized name and description based on current language
  const getLocalizedName = () => {
    if (language === 'en') return achievement.nameEn;
    if (language === 'zh-TW') return achievement.nameZhTW;
    return achievement.name; // zh (simplified)
  };

  const getLocalizedDescription = () => {
    if (language === 'en') return achievement.descriptionEn;
    if (language === 'zh-TW') return achievement.descriptionZhTW;
    return achievement.description; // zh (simplified)
  };

  return (
    <div
      style={{
        position: 'fixed',
        bottom: '2rem',
        right: '2rem',
        zIndex: 1000,
        animation: 'slideInUp 0.5s ease-out',
      }}
    >
      <div
        style={{
          padding: '1.25rem 1.5rem',
          background: style.bg,
          borderRadius: '16px',
          border: `2px solid ${style.border}`,
          boxShadow: `${style.glow}, 0 10px 40px rgba(0,0,0,0.15)`,
          display: 'flex',
          alignItems: 'center',
          gap: '1rem',
          maxWidth: '360px',
        }}
      >
        <div
          style={{
            width: '52px',
            height: '52px',
            borderRadius: '14px',
            background: 'white',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '1.75rem',
            boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          }}
        >
          {achievement.icon}
        </div>
        <div style={{ flex: 1 }}>
          <div
            style={{
              fontSize: '0.75rem',
              fontWeight: 600,
              color: style.text,
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
              marginBottom: '0.25rem',
            }}
          >
            {t('achievements.notification')}
          </div>
          <div style={{ fontWeight: 700, fontSize: '1rem', color: '#1c1917', marginBottom: '0.25rem' }}>
            {getLocalizedName()}
          </div>
          <div style={{ fontSize: '0.813rem', color: '#57534e' }}>{getLocalizedDescription()}</div>
        </div>
        <button
          onClick={onDismiss}
          style={{
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            fontSize: '1.25rem',
            color: '#a8a29e',
            padding: '0.25rem',
          }}
        >
          ×
        </button>
      </div>

      <style jsx>{`
        @keyframes slideInUp {
          from {
            transform: translateY(100px);
            opacity: 0;
          }
          to {
            transform: translateY(0);
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}

// 成就弹窗组件
interface AchievementsModalProps {
  onClose: () => void;
}

export function AchievementsModal({ onClose }: AchievementsModalProps) {
  const { t } = useLanguage();
  const { achievements, totalPoints } = useAchievements();

  const unlockedCount = achievements.filter((a) => a.unlocked).length;
  const categories = ['assessment', 'learning', 'milestone', 'special'] as const;

  // 点击背景关闭弹窗
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      onClick={handleBackdropClick}
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
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'white',
          borderRadius: '20px',
          maxWidth: '600px',
          width: '100%',
          maxHeight: '85vh',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* 头部 */}
        <div
          style={{
            padding: '1.25rem 1.5rem',
            borderBottom: '1px solid var(--gray-100)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'linear-gradient(135deg, rgba(254,243,199,0.3), rgba(253,230,138,0.2))',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '12px',
                background: 'linear-gradient(135deg, #fef3c7, #fde68a)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.25rem',
                boxShadow: '0 2px 8px rgba(251, 191, 36, 0.3)',
              }}
            >
              🏆
            </span>
            <div>
              <h3 style={{ fontWeight: 700, fontSize: '1.125rem', color: '#92400e', margin: 0 }}>
                {t('achievements.system')}
              </h3>
              <p style={{ fontSize: '0.75rem', color: '#a8a29e', margin: '0.125rem 0 0 0' }}>
                {fmt2(unlockedCount)} / {fmt2(achievements.length)} {t('achievements.unlocked')}
              </p>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <span
              style={{
                fontWeight: 700,
                color: '#b45309',
                background: 'linear-gradient(135deg, #fef3c7, #fde68a)',
                padding: '0.5rem 1rem',
                borderRadius: '10px',
                fontSize: '0.9375rem',
                boxShadow: '0 2px 8px rgba(251, 191, 36, 0.2)',
              }}
            >
              {fmt2(totalPoints)} {t('achievements.points')}
            </span>
            <button
              onClick={onClose}
              style={{
                background: 'transparent',
                border: 'none',
                fontSize: '1.5rem',
                cursor: 'pointer',
                color: 'var(--gray-400)',
                lineHeight: 1,
                padding: '0.25rem',
                borderRadius: '8px',
                transition: 'all 0.2s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--gray-100)';
                e.currentTarget.style.color = 'var(--gray-600)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.color = 'var(--gray-400)';
              }}
            >
              ×
            </button>
          </div>
        </div>

        {/* 内容区域 */}
        <div
          style={{
            padding: '1.5rem',
            overflowY: 'auto',
            flex: 1,
          }}
        >
          {categories.map((category) => {
            const categoryAchievements = achievements.filter((a) => a.category === category);
            if (categoryAchievements.length === 0) return null;

            return (
              <div key={category} style={{ marginBottom: '1.5rem' }}>
                <h4
                  style={{
                    fontSize: '0.875rem',
                    fontWeight: 600,
                    color: '#57534e',
                    marginBottom: '0.75rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    padding: '0.5rem 0.75rem',
                    background: 'var(--gray-50)',
                    borderRadius: '8px',
                  }}
                >
                  {categoryIcons[category]}
                  {t(categoryLabelKeys[category])}
                </h4>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                    gap: '0.75rem',
                  }}
                >
                  {categoryAchievements.map((achievement) => (
                    <AchievementItem key={achievement.id} achievement={achievement} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* 底部 */}
        <div
          style={{
            padding: '1rem 1.5rem',
            borderTop: '1px solid var(--gray-100)',
            display: 'flex',
            justifyContent: 'center',
            gap: '1rem',
            background: 'var(--gray-50)',
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: '0.625rem 1.5rem',
              borderRadius: '10px',
              border: '1px solid var(--gray-200)',
              background: 'white',
              color: 'var(--gray-600)',
              fontWeight: 500,
              fontSize: '0.875rem',
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'var(--sage)';
              e.currentTarget.style.color = 'var(--sage-dark)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--gray-200)';
              e.currentTarget.style.color = 'var(--gray-600)';
            }}
          >
            {t('common.close')}
          </button>
        </div>
      </div>
    </div>
  );
}

// 成就项组件（用于弹窗内）
interface AchievementItemProps {
  achievement: Achievement;
}

function AchievementItem({ achievement }: AchievementItemProps) {
  const { t, language } = useLanguage();
  const style = rarityStyleMap[achievement.rarity];

  const getLocalizedName = () => {
    if (language === 'zh') return achievement.name;
    if (language === 'zh-TW') return achievement.nameZhTW || achievement.name;
    return achievement.nameEn || achievement.name;
  };

  const getLocalizedDescription = () => {
    if (language === 'zh') return achievement.description;
    if (language === 'zh-TW') return achievement.descriptionZhTW || achievement.description;
    return achievement.descriptionEn || achievement.description;
  };

  return (
    <div
      style={{
        background: achievement.unlocked ? style.bg : '#f5f5f4',
        border: `1px solid ${achievement.unlocked ? style.border : '#e7e5e4'}`,
        borderRadius: '12px',
        padding: '0.875rem',
        opacity: achievement.unlocked ? 1 : 0.6,
        transition: 'all 0.2s ease',
        boxShadow: achievement.unlocked ? style.glow : 'none',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
        <div
          style={{
            width: '40px',
            height: '40px',
            borderRadius: '10px',
            background: achievement.unlocked
              ? 'rgba(255,255,255,0.6)'
              : 'var(--gray-200)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '1.25rem',
            flexShrink: 0,
          }}
        >
          {achievement.unlocked ? achievement.icon : '🔒'}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: '0.6875rem',
              fontWeight: 600,
              color: style.text,
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
              marginBottom: '0.25rem',
            }}
          >
            {t(rarityLabelKeys[achievement.rarity])}
          </div>
          <div
            style={{
              fontWeight: 600,
              fontSize: '0.875rem',
              color: achievement.unlocked ? '#1c1917' : '#a8a29e',
              marginBottom: '0.25rem',
              lineHeight: 1.3,
            }}
          >
            {getLocalizedName()}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#78716c', lineHeight: 1.4 }}>
            {getLocalizedDescription()}
          </div>
          {achievement.unlocked && achievement.unlockedAt && (
            <div
              style={{
                marginTop: '0.5rem',
                fontSize: '0.6875rem',
                color: '#a8a29e',
              }}
            >
              {new Date(achievement.unlockedAt).toLocaleDateString()}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
