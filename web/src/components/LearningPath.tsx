'use client';

import { useEffect } from 'react';
import { useLearningPath, LearningRecommendation } from '@/lib/hooks';
import { useLanguage } from '@/lib/contexts';

const typeIconMap: Record<LearningRecommendation['type'], string> = {
  course: '📚',
  project: '💻',
  assessment: '📝',
  resource: '🔗',
};

const typeLabelKeys: Record<LearningRecommendation['type'], string> = {
  course: 'learning.typeCourse',
  project: 'learning.typeProject',
  assessment: 'learning.typeAssessment',
  resource: 'learning.typeResource',
};

const priorityStyleMap: Record<LearningRecommendation['priority'], { bg: string; color: string; labelKey: string }> = {
  high: { bg: '#fef2f2', color: '#dc2626', labelKey: 'learning.priorityHigh' },
  medium: { bg: '#fefce8', color: '#ca8a04', labelKey: 'learning.priorityMedium' },
  low: { bg: '#f0fdf4', color: '#16a34a', labelKey: 'learning.priorityLow' },
};

interface RecommendationItemProps {
  recommendation: LearningRecommendation;
  index: number;
}

function RecommendationItem({ recommendation, index }: RecommendationItemProps) {
  const { t } = useLanguage();
  const priorityStyle = priorityStyleMap[recommendation.priority];

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '1rem',
        padding: '1rem',
        background: 'white',
        borderRadius: '12px',
        border: '1px solid var(--gray-200)',
        transition: 'all 0.2s ease',
        cursor: 'pointer',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'var(--sage)';
        e.currentTarget.style.boxShadow = '0 4px 12px rgba(152, 184, 168, 0.15)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--gray-200)';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      <div
        style={{
          width: '32px',
          height: '32px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, var(--sage), var(--sage-dark))',
          color: 'white',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 700,
          fontSize: '0.875rem',
          flexShrink: 0,
        }}
      >
        {index + 1}
      </div>

      <div
        style={{
          width: '44px',
          height: '44px',
          borderRadius: '10px',
          background: 'var(--gray-50)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '1.5rem',
          flexShrink: 0,
        }}
      >
        {recommendation.icon || typeIconMap[recommendation.type]}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            marginBottom: '0.25rem',
          }}
        >
          <span style={{ fontWeight: 600, fontSize: '0.9375rem', color: 'var(--gray-900)' }}>
            {recommendation.title}
          </span>
          <span
            style={{
              fontSize: '0.625rem',
              fontWeight: 600,
              padding: '0.125rem 0.375rem',
              borderRadius: '4px',
              background: priorityStyle.bg,
              color: priorityStyle.color,
            }}
          >
            {t(priorityStyle.labelKey)}
          </span>
        </div>
        <div
          style={{
            fontSize: '0.8125rem',
            color: 'var(--gray-500)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {recommendation.description}
        </div>
      </div>

      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <div
          style={{
            fontSize: '0.75rem',
            fontWeight: 500,
            color: 'var(--gray-400)',
            marginBottom: '0.25rem',
          }}
        >
          {t(typeLabelKeys[recommendation.type])}
        </div>
        <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--sage-dark)' }}>
          ~{recommendation.estimatedHours}h
        </div>
      </div>

      <div
        style={{
          color: 'var(--gray-300)',
          fontSize: '1.25rem',
          flexShrink: 0,
        }}
      >
        →
      </div>
    </div>
  );
}

interface LearningPathCardProps {
  skills: { name: string; level: number }[];
  targetRole?: string;
  maxItems?: number;
}

export function LearningPathCard({ skills, targetRole, maxItems = 5 }: LearningPathCardProps) {
  const { t } = useLanguage();
  const { recommendations, skillGaps, loading, generateRecommendations } = useLearningPath();

  useEffect(() => {
    if (skills.length > 0) {
      generateRecommendations(skills, targetRole);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(skills), targetRole]);

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '2rem',
          color: 'var(--gray-500)',
        }}
      >
        <div className="spinner" style={{ marginRight: '0.75rem' }}></div>
        {t('learning.generating')}
      </div>
    );
  }

  if (recommendations.length === 0) {
    return (
      <div
        style={{
          textAlign: 'center',
          padding: '2rem',
          color: 'var(--gray-500)',
        }}
      >
        <div style={{ fontSize: '2rem', marginBottom: '0.75rem' }}>🎯</div>
        <div style={{ fontWeight: 500 }}>{t('learning.noSuggestions')}</div>
        <div style={{ fontSize: '0.875rem', marginTop: '0.25rem' }}>
          {t('learning.uploadMore')}
        </div>
      </div>
    );
  }

  const displayItems = recommendations.slice(0, maxItems);

  return (
    <div>
      {skillGaps.length > 0 && (
        <div
          style={{
            display: 'flex',
            gap: '0.5rem',
            marginBottom: '1rem',
            flexWrap: 'wrap',
          }}
        >
          {skillGaps.slice(0, 3).map((gap) => (
            <span
              key={gap.skill}
              style={{
                fontSize: '0.75rem',
                padding: '0.375rem 0.625rem',
                borderRadius: '6px',
                background:
                  gap.gap >= 2 ? '#fef2f2' : gap.gap === 1 ? '#fefce8' : '#f0fdf4',
                color: gap.gap >= 2 ? '#dc2626' : gap.gap === 1 ? '#ca8a04' : '#16a34a',
                display: 'flex',
                alignItems: 'center',
                gap: '0.25rem',
              }}
            >
              <span>{gap.skill}</span>
              <span style={{ opacity: 0.7 }}>
                Lv.{gap.currentLevel} → Lv.{gap.targetLevel}
              </span>
            </span>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {displayItems.map((rec, index) => (
          <RecommendationItem key={rec.id} recommendation={rec} index={index} />
        ))}
      </div>

      {recommendations.length > maxItems && (
        <div style={{ textAlign: 'center', marginTop: '1rem' }}>
          <button
            className="btn btn-ghost btn-sm"
            style={{ color: 'var(--sage-dark)' }}
          >
            {t('learning.viewAll')} {recommendations.length} {t('learning.suggestions')} →
          </button>
        </div>
      )}
    </div>
  );
}

interface FullLearningPathProps {
  skills: { name: string; level: number }[];
  targetRole?: string;
}

export function FullLearningPath({ skills, targetRole }: FullLearningPathProps) {
  const { t } = useLanguage();
  const { recommendations, skillGaps, loading, generateRecommendations } = useLearningPath();

  useEffect(() => {
    generateRecommendations(skills, targetRole);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(skills), targetRole]);

  if (loading) {
    return (
      <div className="loading" style={{ padding: '3rem' }}>
        <span className="spinner"></span>
        {t('learning.analyzing')}
      </div>
    );
  }

  return (
    <div>
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-header">
          <h3 className="card-title">
            <span style={{ marginRight: '0.5rem' }}>📊</span>
            {t('learning.skillGapTitle')}
          </h3>
        </div>
        <div className="card-content">
          {skillGaps.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--gray-500)' }}>
              {t('learning.excellent')}
            </div>
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                gap: '1rem',
              }}
            >
              {skillGaps.map((gap) => (
                <div
                  key={gap.skill}
                  style={{
                    padding: '1rem',
                    background: 'var(--gray-50)',
                    borderRadius: '12px',
                    border: '1px solid var(--gray-200)',
                  }}
                >
                  <div
                    style={{
                      fontWeight: 600,
                      marginBottom: '0.5rem',
                      color: 'var(--gray-900)',
                    }}
                  >
                    {gap.skill}
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      fontSize: '0.875rem',
                    }}
                  >
                    <span
                      style={{
                        padding: '0.25rem 0.5rem',
                        borderRadius: '6px',
                        background: 'white',
                        border: '1px solid var(--gray-200)',
                      }}
                    >
                      {t('learning.current')}{gap.currentLevel}
                    </span>
                    <span style={{ color: 'var(--gray-400)' }}>→</span>
                    <span
                      style={{
                        padding: '0.25rem 0.5rem',
                        borderRadius: '6px',
                        background: 'var(--sage-light)',
                        color: 'var(--sage-dark)',
                        fontWeight: 600,
                      }}
                    >
                      {t('learning.target')}{gap.targetLevel}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3 className="card-title">
            <span style={{ marginRight: '0.5rem' }}>🎯</span>
            {t('learning.pathTitle')}
          </h3>
          <span style={{ color: 'var(--gray-500)', fontSize: '0.875rem' }}>
            {recommendations.length} {t('learning.count')}
          </span>
        </div>
        <div className="card-content">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {recommendations.map((rec, index) => (
              <RecommendationItem key={rec.id} recommendation={rec} index={index} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
