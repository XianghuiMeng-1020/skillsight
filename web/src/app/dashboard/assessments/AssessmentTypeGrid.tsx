'use client';

type AssessmentType =
  | 'communication'
  | 'programming'
  | 'writing'
  | 'data_analysis'
  | 'problem_solving'
  | 'presentation';

type AssessmentMeta = {
  id: AssessmentType;
  titleKey: string;
  icon: string;
  descKey: string;
  timeKey: string;
  featuresKeys: string[];
};

type Props = {
  assessments: AssessmentMeta[];
  activeTab: AssessmentType;
  onSelect: (id: AssessmentType) => void;
  onPreview: (id: AssessmentType) => void;
  getCoverageDesc: (type: AssessmentType) => string | null;
  t: (key: string) => string;
};

export function AssessmentTypeGrid({
  assessments,
  activeTab,
  onSelect,
  onPreview,
  getCoverageDesc,
  t,
}: Props) {
  return (
    <div className="assessment-grid" style={{ marginBottom: '2rem' }}>
      {assessments.map((assessment) => (
        <div
          key={assessment.id}
          className={`assessment-card ${activeTab === assessment.id ? 'selected' : ''}`}
          style={{ cursor: 'pointer' }}
          onClick={() => onSelect(assessment.id)}
          role="button"
          tabIndex={0}
          aria-pressed={activeTab === assessment.id}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onSelect(assessment.id);
            }
          }}
        >
          <div className="assessment-header">
            <div className="assessment-icon">{assessment.icon}</div>
            <div className="assessment-title">{t(assessment.titleKey)}</div>
            <div className="assessment-subtitle">{t(assessment.descKey)}</div>
            {getCoverageDesc(assessment.id) && (
              <div style={{ marginTop: '0.35rem', fontSize: '0.75rem', color: 'var(--gray-600)' }}>
                {getCoverageDesc(assessment.id)}
              </div>
            )}
          </div>
          <div className="assessment-content">
            <div style={{ fontSize: '0.875rem', color: 'var(--gray-500)', marginBottom: '0.75rem' }}>
              ⏱️ {t(assessment.timeKey)}
            </div>
            <ul className="assessment-features">
              {assessment.featuresKeys.map((fk, i) => (
                <li key={i}>{t(fk)}</li>
              ))}
            </ul>
          </div>
          <div className="assessment-footer">
            <div style={{ display: 'flex', width: '100%', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
              {activeTab === assessment.id ? (
                <span className="badge badge-primary">{t('assessmentsList.selected')}</span>
              ) : (
                <span style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>{t('assessmentsList.clickToSelect')}</span>
              )}
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onPreview(assessment.id);
                }}
              >
                {t('assessmentsList.previewButton')}
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
