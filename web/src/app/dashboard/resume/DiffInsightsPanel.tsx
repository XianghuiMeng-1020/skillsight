'use client';

import styles from './resume.module.css';

type DiffInsights = {
  role_keywords: string[];
  highlights: string[];
  risks: Array<{ level: string; code: string; message: string }>;
  next_actions: string[];
  dimension_impact: Record<string, { delta: number; signal: 'positive' | 'neutral' | 'negative' }>;
  semantic_alignment: {
    avg_similarity: number;
    matched_sentences: number;
    added_sentences: number;
    removed_sentences: number;
  };
  risk_validator: {
    risk_level: 'low' | 'medium' | 'high' | string;
    issues: Array<{ level: string; code: string; message: string }>;
  };
  attribution: {
    total_delta?: number | null;
    by_dimension: Array<{
      dimension: string;
      score_before: number;
      score_after: number;
      score_delta: number;
      alignment: 'aligned' | 'mixed' | 'neutral' | string;
    }>;
  };
};

type Props = {
  diffInsights: DiffInsights;
  t: (key: string) => string;
};

export function DiffInsightsPanel({ diffInsights, t }: Props) {
  return (
    <div className={styles.semanticPanel}>
      <div className={styles.semanticTitle}>{t('resume.semanticInsightsTitle') || 'Semantic Change Insights'}</div>
      {!!diffInsights.role_keywords?.length && (
        <div className={styles.semanticKeywords}>
          {(t('resume.roleKeywords') || 'Role keywords')}: {diffInsights.role_keywords.join(', ')}
        </div>
      )}
      <div className={styles.impactGrid}>
        {Object.entries(diffInsights.dimension_impact).map(([k, v]) => (
          <span key={k} className={`${styles.impactChip} ${v.signal === 'positive' ? styles.impactPos : v.signal === 'negative' ? styles.impactNeg : styles.impactNeu}`}>
            {k}: {v.delta > 0 ? `+${v.delta}` : v.delta}
          </span>
        ))}
      </div>
      <div className={styles.semanticSummaryRow}>
        <span>{(t('resume.semanticAvgSimilarity') || 'Avg similarity')}: {Math.round((diffInsights.semantic_alignment?.avg_similarity || 0) * 100)}%</span>
        <span>{(t('resume.semanticMatched') || 'Matched')}: {diffInsights.semantic_alignment?.matched_sentences || 0}</span>
        <span>{(t('resume.semanticAddedSentences') || 'Added')}: {diffInsights.semantic_alignment?.added_sentences || 0}</span>
        <span>{(t('resume.semanticRemovedSentences') || 'Removed')}: {diffInsights.semantic_alignment?.removed_sentences || 0}</span>
      </div>
      <div className={styles.semanticRiskBadgeRow}>
        <span className={`${styles.riskBadge} ${
          diffInsights.risk_validator?.risk_level === 'high'
            ? styles.riskHigh
            : (diffInsights.risk_validator?.risk_level === 'medium' ? styles.riskMedium : styles.riskLow)
        }`}>
          {(t('resume.riskLevel') || 'Risk level')}: {diffInsights.risk_validator?.risk_level || 'low'}
        </span>
      </div>
      {!!diffInsights.attribution?.by_dimension?.length && (
        <div className={styles.attrList}>
          {diffInsights.attribution.by_dimension.map((it, idx) => (
            <div key={`attr-${idx}`} className={styles.attrItem}>
              <span className={styles.attrLabel}>{it.dimension}</span>
              <span className={`${styles.attrDelta} ${it.score_delta > 0 ? styles.attrPos : (it.score_delta < 0 ? styles.attrNeg : styles.attrNeu)}`}>
                {it.score_delta > 0 ? `+${it.score_delta}` : it.score_delta}
              </span>
            </div>
          ))}
          {typeof diffInsights.attribution.total_delta === 'number' && (
            <div className={styles.attrTotal}>
              {(t('resume.totalDelta') || 'Total delta')}: {diffInsights.attribution.total_delta > 0 ? '+' : ''}{diffInsights.attribution.total_delta}
            </div>
          )}
        </div>
      )}
      {!!diffInsights.highlights?.length && (
        <ul className={styles.semanticList}>
          {diffInsights.highlights.map((h, idx) => <li key={`hl-${idx}`}>{h}</li>)}
        </ul>
      )}
      {!!diffInsights.risks?.length && (
        <ul className={styles.semanticRiskList}>
          {diffInsights.risks.map((r, idx) => <li key={`rk-${idx}`}>{r.message}</li>)}
        </ul>
      )}
      {!!diffInsights.risk_validator?.issues?.length && (
        <ul className={styles.semanticRiskList}>
          {diffInsights.risk_validator.issues.map((r, idx) => <li key={`rv-${idx}`}>{r.message}</li>)}
        </ul>
      )}
      {!!diffInsights.next_actions?.length && (
        <ul className={styles.semanticList}>
          {diffInsights.next_actions.map((a, idx) => <li key={`na-${idx}`}>{a}</li>)}
        </ul>
      )}
    </div>
  );
}
