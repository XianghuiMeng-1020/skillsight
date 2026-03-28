'use client';

import { useAchievements, Achievement } from '@/lib/hooks';
import { useLanguage, getDateLocale } from '@/lib/contexts';

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
            {achievement.unlocked ? t('achievements.unlocked') : `${Math.round(progress)}%`}
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
            {unlockedCount} / {achievements.length} {t('achievements.unlocked')}
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
            {totalPoints} {t('achievements.points')}
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
