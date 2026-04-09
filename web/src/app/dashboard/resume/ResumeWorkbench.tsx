'use client';

import { useEffect, useMemo, useState } from 'react';
import { useLanguage } from '@/lib/contexts';
import { useToast } from '@/components/Toast';
import { studentBff } from '@/lib/bffClient';
import styles from './resume.module.css';
import { DiffInsightsPanel } from './DiffInsightsPanel';

interface ResumeWorkbenchProps {
  reviewId: string;
  onResumeOverrideChange: (text: string) => void;
  onTemplateOptionsChange: (opts: Record<string, unknown>) => void;
}

type DiffMark = 'same' | 'added' | 'removed' | 'empty';
type DiffRow = { left: string; right: string; leftMark: DiffMark; rightMark: DiffMark };
type ResumeSections = { order: string[]; blocks: Record<string, string[]> };
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

function base64ToBlob(base64: string, mime: string): Blob {
  const binary = atob(base64 || '');
  const arr = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) arr[i] = binary.charCodeAt(i);
  return new Blob([arr], { type: mime || 'application/octet-stream' });
}

function extractWords(text: string): string[] {
  return (text.match(/[A-Za-z0-9+#./-]{2,}|[\u4e00-\u9fff]{1,}/g) || []).map((w) => w.toLowerCase());
}

function normalizeSectionHeader(line: string): string | null {
  const n = line.trim().toLowerCase().replace(/[：:]/g, '').replace(/\s+/g, ' ');
  if (!n) return null;
  if (['summary', 'profile', 'objective', 'personal statement', '个人简介', '简介', '摘要'].includes(n)) return 'summary';
  if (['experience', 'work experience', 'professional experience', 'work history', '工作经历', '工作经验', '职业经历', '履历'].includes(n)) return 'experience';
  if (['education', 'education history', 'academic background', '教育背景', '教育经历', '学历'].includes(n)) return 'education';
  if (['projects', 'project experience', 'project history', '项目', '项目经历', '项目经验'].includes(n)) return 'projects';
  if (['skills', 'technical skills', 'core competencies', 'competencies', '技能', '专业技能', '技术技能', '核心技能'].includes(n)) return 'skills';
  if (['certifications', 'certificates', 'licenses', '证书', '资格证书'].includes(n)) return 'certifications';
  if (['awards', 'honors', 'achievements', '获奖', '荣誉', '奖项'].includes(n)) return 'awards';
  return null;
}

function splitResumeSections(text: string): ResumeSections {
  const blocks: Record<string, string[]> = { general: [] };
  const order: string[] = ['general'];
  let current = 'general';
  for (const raw of (text || '').split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    const maybeSec = normalizeSectionHeader(line);
    if (maybeSec) {
      current = maybeSec;
      if (!blocks[current]) blocks[current] = [];
      if (!order.includes(current)) order.push(current);
      continue;
    }
    blocks[current] = blocks[current] || [];
    blocks[current].push(line);
  }
  return { order, blocks };
}

function buildGreedyDiff(currentText: string, baselineText: string): DiffRow[] {
  const current = (currentText || '')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
  const baseline = (baselineText || '')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < baseline.length || j < current.length) {
    const left = baseline[i];
    const right = current[j];
    if (left !== undefined && right !== undefined && left === right) {
      rows.push({ left, right, leftMark: 'same', rightMark: 'same' });
      i += 1;
      j += 1;
      continue;
    }
    if (right !== undefined && baseline[i] !== undefined && current[j + 1] === baseline[i]) {
      rows.push({ left: '', right, leftMark: 'empty', rightMark: 'added' });
      j += 1;
      continue;
    }
    if (left !== undefined && current[j] !== undefined && baseline[i + 1] === current[j]) {
      rows.push({ left, right: '', leftMark: 'removed', rightMark: 'empty' });
      i += 1;
      continue;
    }
    rows.push({
      left: left || '',
      right: right || '',
      leftMark: left ? 'removed' : 'empty',
      rightMark: right ? 'added' : 'empty',
    });
    i += left ? 1 : 0;
    j += right ? 1 : 0;
  }
  return rows.slice(0, 220);
}

function buildSideBySideDiff(currentText: string, baselineText: string): DiffRow[] {
  const current = (currentText || '')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
  const baseline = (baselineText || '')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);

  // Avoid expensive O(n*m) matrix for extreme inputs.
  if (baseline.length * current.length > 45000) {
    return buildGreedyDiff(currentText, baselineText);
  }

  const n = baseline.length;
  const m = current.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => Array<number>(m + 1).fill(0));

  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      if (baseline[i] === current[j]) dp[i][j] = dp[i + 1][j + 1] + 1;
      else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (baseline[i] === current[j]) {
      rows.push({ left: baseline[i], right: current[j], leftMark: 'same', rightMark: 'same' });
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      rows.push({ left: baseline[i], right: '', leftMark: 'removed', rightMark: 'empty' });
      i += 1;
    } else {
      rows.push({ left: '', right: current[j], leftMark: 'empty', rightMark: 'added' });
      j += 1;
    }
  }
  while (i < n) {
    rows.push({ left: baseline[i], right: '', leftMark: 'removed', rightMark: 'empty' });
    i += 1;
  }
  while (j < m) {
    rows.push({ left: '', right: current[j], leftMark: 'empty', rightMark: 'added' });
    j += 1;
  }
  return rows.slice(0, 260);
}

export function ResumeWorkbench({
  reviewId,
  onResumeOverrideChange,
  onTemplateOptionsChange,
}: ResumeWorkbenchProps) {
  const { t } = useLanguage();
  const { addToast } = useToast();
  const [resumeText, setResumeText] = useState('');
  const [loading, setLoading] = useState(true);
  const [estimatedPages, setEstimatedPages] = useState<number | null>(null);
  const [hints, setHints] = useState<string[]>([]);
  const [fontScale, setFontScale] = useState(100);
  const [lineSpacing, setLineSpacing] = useState(110);
  const [accentColor, setAccentColor] = useState<'default' | 'teal' | 'blue' | 'gold'>('default');
  const [cloneRoleId, setCloneRoleId] = useState('');
  const [cloning, setCloning] = useState(false);
  const [reviews, setReviews] = useState<Array<{ review_id: string; status?: string; total_initial?: number; total_final?: number }>>([]);
  const [compareReviewId, setCompareReviewId] = useState('');
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareStats, setCompareStats] = useState<{ added: number; removed: number; overlap: number } | null>(null);
  const [compareCurrentText, setCompareCurrentText] = useState('');
  const [compareSourceText, setCompareSourceText] = useState('');
  const [compareMode, setCompareMode] = useState<'all' | 'changes'>('changes');
  const [compareSection, setCompareSection] = useState<string>('all');
  const [diffInsights, setDiffInsights] = useState<DiffInsights | null>(null);
  const [exportingReport, setExportingReport] = useState<'docx' | 'pdf' | null>(null);
  const [compareDiffRows, setCompareDiffRows] = useState<DiffRow[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [editable, comp, list] = await Promise.all([
          studentBff.resumeReviewEditableResume(reviewId),
          studentBff.resumeReviewCompressionHints(reviewId),
          studentBff.getResumeReviews(12, 0),
        ]);
        if (cancelled) return;
        setResumeText(editable.resume_text || '');
        setEstimatedPages(comp.estimated_pages);
        setHints(comp.hints || []);
        setReviews((list.reviews || []).filter((r) => r.review_id !== reviewId));
      } catch (e) {
        if (!cancelled) {
          addToast('error', e instanceof Error ? e.message : t('common.error'));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reviewId, addToast, t]);

  useEffect(() => {
    onResumeOverrideChange(resumeText);
  }, [resumeText, onResumeOverrideChange]);

  const opts = useMemo(
    () => ({
      font_scale_pct: fontScale,
      line_spacing_pct: lineSpacing,
      accent_color: accentColor,
    }),
    [fontScale, lineSpacing, accentColor]
  );

  useEffect(() => {
    onTemplateOptionsChange(opts);
  }, [opts, onTemplateOptionsChange]);

  const handleClone = async () => {
    setCloning(true);
    try {
      const out = await studentBff.resumeReviewCloneVersion(reviewId, {
        targetRoleId: cloneRoleId.trim() || undefined,
        label: `${t('resume.versionLabelPrefix') || 'Version'} ${new Date().toLocaleTimeString()}`,
      });
      addToast('success', `${t('resume.versionCloned') || 'Version created'}: ${out.review_id.slice(0, 8)}`);
    } catch (e) {
      addToast('error', e instanceof Error ? e.message : t('common.error'));
    } finally {
      setCloning(false);
    }
  };

  const handleCompare = async () => {
    if (!compareReviewId) return;
    setCompareLoading(true);
    try {
      const [current, other, insights] = await Promise.all([
        studentBff.resumeReviewEditableResume(reviewId),
        studentBff.resumeReviewEditableResume(compareReviewId),
        studentBff.resumeReviewDiffInsights(reviewId, {
          compareReviewId,
          resumeOverrideText: resumeText.trim() || undefined,
        }),
      ]);
      const curLines = new Set(
        (current.resume_text || "")
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean)
      );
      const otherLines = new Set(
        (other.resume_text || "")
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean)
      );
      let overlap = 0;
      for (const ln of curLines) {
        if (otherLines.has(ln)) overlap += 1;
      }
      const removed = [...otherLines].filter((ln) => !curLines.has(ln)).length;
      const added = [...curLines].filter((ln) => !otherLines.has(ln)).length;
      setCompareStats({ added, removed, overlap });
      setCompareCurrentText(current.resume_text || '');
      setCompareSourceText(other.resume_text || '');
      setCompareSection('all');
      setCompareMode('changes');
      setDiffInsights({
        role_keywords: insights.role_keywords || [],
        highlights: insights.highlights || [],
        risks: insights.risks || [],
        next_actions: insights.next_actions || [],
        dimension_impact: insights.dimension_impact || {},
        semantic_alignment: insights.semantic_alignment || {
          avg_similarity: 0,
          matched_sentences: 0,
          added_sentences: 0,
          removed_sentences: 0,
        },
        risk_validator: insights.risk_validator || { risk_level: 'low', issues: [] },
        attribution: insights.attribution || { total_delta: null, by_dimension: [] },
      });
    } catch (e) {
      addToast('error', e instanceof Error ? e.message : t('common.error'));
      setCompareStats(null);
      setCompareCurrentText('');
      setCompareSourceText('');
      setCompareSection('all');
      setDiffInsights(null);
      setCompareDiffRows([]);
    } finally {
      setCompareLoading(false);
    }
  };

  const handleLoadComparedVersion = () => {
    if (!compareSourceText) return;
    setResumeText(compareSourceText);
    addToast('success', t('resume.loadedComparedVersion') || 'Loaded compared version to editor');
  };

  const handleAppendAddedOnly = () => {
    if (!visibleRows.length) return;
    const addedLines = visibleRows
      .filter((row) => row.rightMark === 'added' && row.right.trim())
      .map((row) => row.right.trim());
    if (!addedLines.length) {
      addToast('error', t('resume.noAddedLinesToAppend') || 'No added lines');
      return;
    }
    const existing = new Set(
      resumeText
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean)
    );
    const toAppend = addedLines.filter((ln) => !existing.has(ln));
    if (!toAppend.length) {
      addToast('error', t('resume.noAddedLinesToAppend') || 'No added lines');
      return;
    }
    setResumeText((prev) => `${prev.trimEnd()}\n${toAppend.join('\n')}\n`);
    addToast('success', (t('resume.appendedAddedLines') || 'Appended {n} added lines').replace('{n}', String(toAppend.length)));
  };

  const handleReplaceWithComparedSection = () => {
    if (compareSection === 'all') {
      handleLoadComparedVersion();
      return;
    }
    if (!selectedBaselineText.trim()) return;
    setResumeText((prev) => {
      const prevSections = splitResumeSections(prev);
      const nextLines: string[] = [];
      for (const key of prevSections.order) {
        if (key === 'general' || !prevSections.blocks[key]?.length) continue;
        nextLines.push(key.toUpperCase());
        if (key === compareSection) {
          nextLines.push(...selectedBaselineText.split('\n').map((s) => s.trim()).filter(Boolean));
        } else {
          nextLines.push(...prevSections.blocks[key]);
        }
        nextLines.push('');
      }
      if (!nextLines.length) return selectedBaselineText;
      return nextLines.join('\n').trim();
    });
    addToast('success', t('resume.replacedComparedSection') || 'Replaced selected section from compared version');
  };

  const handleExportReport = async (format: 'docx' | 'pdf') => {
    setExportingReport(format);
    try {
      const out = await studentBff.resumeReviewExportAttributionReport(reviewId, {
        exportFormat: format,
        compareReviewId: compareReviewId || undefined,
        resumeOverrideText: resumeText.trim() || undefined,
      });
      const blob = base64ToBlob(out.content_base64, out.mime_type);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = out.filename || (format === 'pdf' ? 'resume_explainability.pdf' : 'resume_explainability.docx');
      a.click();
      URL.revokeObjectURL(url);
      if (out.pdf_unavailable && format === 'pdf') {
        addToast('success', `${t('resume.exportReportSuccess') || 'Report exported'} — ${t('resume.pdfFallbackNote')}`);
      } else {
        addToast('success', t('resume.exportReportSuccess') || 'Report exported');
      }
    } catch (e) {
      addToast('error', e instanceof Error ? e.message : t('common.error'));
    } finally {
      setExportingReport(null);
    }
  };

  const currentSections = useMemo(() => splitResumeSections(compareCurrentText), [compareCurrentText]);
  const baselineSections = useMemo(() => splitResumeSections(compareSourceText), [compareSourceText]);
  const sectionOptions = useMemo(() => {
    const keys = new Set<string>(['all']);
    for (const key of [...currentSections.order, ...baselineSections.order]) {
      if (key === 'general') continue;
      if ((currentSections.blocks[key]?.length || 0) > 0 || (baselineSections.blocks[key]?.length || 0) > 0) {
        keys.add(key);
      }
    }
    return Array.from(keys);
  }, [currentSections, baselineSections]);

  const selectedBaselineText = useMemo(() => {
    if (compareSection === 'all') return compareSourceText;
    return (baselineSections.blocks[compareSection] || []).join('\n');
  }, [compareSection, compareSourceText, baselineSections]);

  const selectedCurrentText = useMemo(() => {
    if (compareSection === 'all') return compareCurrentText;
    return (currentSections.blocks[compareSection] || []).join('\n');
  }, [compareSection, compareCurrentText, currentSections]);

  useEffect(() => {
    if (!selectedCurrentText && !selectedBaselineText) {
      setCompareDiffRows([]);
      return;
    }
    let cancelled = false;
    try {
      const worker = new Worker(new URL('./diffWorker.ts', import.meta.url));
      worker.onmessage = (event: MessageEvent<DiffRow[]>) => {
        if (!cancelled) setCompareDiffRows(event.data || []);
      };
      worker.onerror = () => {
        if (!cancelled) {
          setCompareDiffRows(buildSideBySideDiff(selectedCurrentText, selectedBaselineText));
        }
      };
      worker.postMessage({
        currentText: selectedCurrentText,
        baselineText: selectedBaselineText,
      });
      return () => {
        cancelled = true;
        worker.terminate();
      };
    } catch {
      setCompareDiffRows(buildSideBySideDiff(selectedCurrentText, selectedBaselineText));
      return () => {
        cancelled = true;
      };
    }
  }, [selectedCurrentText, selectedBaselineText]);

  const baselineWordSet = useMemo(() => new Set(extractWords(selectedBaselineText)), [selectedBaselineText]);
  const currentWordSet = useMemo(() => new Set(extractWords(selectedCurrentText)), [selectedCurrentText]);

  const visibleRows = useMemo(
    () => (compareMode === 'changes'
      ? compareDiffRows.filter((r) => !(r.leftMark === 'same' && r.rightMark === 'same'))
      : compareDiffRows),
    [compareDiffRows, compareMode]
  );

  const sectionLabel = (sec: string) => {
    if (sec === 'all') return t('resume.compareSectionAll') || 'All sections';
    const map: Record<string, string> = {
      summary: t('resume.sectionSummary') || 'Summary',
      experience: t('resume.sectionExperience') || 'Experience',
      education: t('resume.sectionEducation') || 'Education',
      projects: t('resume.sectionProjects') || 'Projects',
      skills: t('resume.sectionSkills') || 'Skills',
      certifications: t('resume.sectionCertifications') || 'Certifications',
      awards: t('resume.sectionAwards') || 'Awards',
      general: t('resume.sectionGeneral') || 'General',
    };
    return map[sec] || sec;
  };

  const renderHighlightedLine = (text: string, mark: DiffMark, side: 'left' | 'right') => {
    if (!text) return ' ';
    if ((side === 'right' && mark !== 'added') || (side === 'left' && mark !== 'removed')) return text;
    const pieces = text.split(/([A-Za-z0-9+#./-]{2,}|[\u4e00-\u9fff]{1,})/g);
    return (
      <>
        {pieces.map((piece, idx) => {
          const w = piece.toLowerCase();
          const isToken = !!piece && /[A-Za-z0-9+#./-]{2,}|[\u4e00-\u9fff]{1,}/.test(piece);
          if (!isToken) return <span key={`${piece}-${idx}`}>{piece}</span>;
          const shouldHighlight = side === 'right' ? !baselineWordSet.has(w) : !currentWordSet.has(w);
          return (
            <span key={`${piece}-${idx}`} className={shouldHighlight ? styles.diffTokenHot : undefined}>
              {piece}
            </span>
          );
        })}
      </>
    );
  };

  if (loading) {
    return <div className={styles.workbench}>{t('common.loading')}</div>;
  }

  return (
    <section className={styles.workbench}>
      <div className={styles.workbenchHeader}>
        <h3 className={styles.workbenchTitle}>{t('resume.workbenchTitle') || 'Export Workbench'}</h3>
        {estimatedPages !== null && (
          <span className={styles.workbenchBadge}>
            {(t('resume.estimatedPages') || 'Estimated pages').replace('{n}', String(estimatedPages))}
          </span>
        )}
      </div>

      <div className={styles.workbenchGrid}>
        <div className={styles.editorPanel}>
          <label className={styles.editorLabel} htmlFor="resume-editor-text">
            {t('resume.liveEditorTitle') || 'Live Resume Editor'}
          </label>
          <textarea
            id="resume-editor-text"
            className={styles.editorTextArea}
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            placeholder={t('resume.liveEditorPlaceholder') || 'Edit resume content before preview/export'}
          />
        </div>

        <div className={styles.controlPanel}>
          <div className={styles.controlBlock}>
            <h4>{t('resume.templateOptionsTitle') || 'Template Options'}</h4>
            <label className={styles.rangeLabel}>
              {(t('resume.optionFontScale') || 'Font scale').replace('{n}', String(fontScale))}
              <input type="range" min={90} max={120} value={fontScale} onChange={(e) => setFontScale(Number(e.target.value))} />
            </label>
            <label className={styles.rangeLabel}>
              {(t('resume.optionLineSpacing') || 'Line spacing').replace('{n}', String(lineSpacing))}
              <input type="range" min={95} max={130} value={lineSpacing} onChange={(e) => setLineSpacing(Number(e.target.value))} />
            </label>
            <label className={styles.selectLabel}>
              {t('resume.optionAccent') || 'Accent color'}
              <select value={accentColor} onChange={(e) => setAccentColor(e.target.value as typeof accentColor)}>
                <option value="default">{t('resume.accentDefault') || 'Default'}</option>
                <option value="teal">{t('resume.accentTeal') || 'Teal'}</option>
                <option value="blue">{t('resume.accentBlue') || 'Blue'}</option>
                <option value="gold">{t('resume.accentGold') || 'Gold'}</option>
              </select>
            </label>
          </div>

          <div className={styles.controlBlock}>
            <h4>{t('resume.compressionHintsTitle') || 'Compression Assistant'}</h4>
            <ul className={styles.hintsList}>
              {hints.map((h, idx) => (
                <li key={`${h}-${idx}`}>{h}</li>
              ))}
            </ul>
          </div>

          <div className={styles.controlBlock}>
            <h4>{t('resume.versioningTitle') || 'Versioning'}</h4>
            <label className={styles.selectLabel}>
              {t('resume.versionTargetRole') || 'Target role (optional)'}
              <input
                type="text"
                value={cloneRoleId}
                onChange={(e) => setCloneRoleId(e.target.value)}
                placeholder={t('resume.versionTargetRolePlaceholder') || 'Enter role id'}
              />
            </label>
            <button type="button" className="btn btn-secondary btn-sm" onClick={handleClone} disabled={cloning}>
              {cloning ? t('common.loading') : (t('resume.cloneVersion') || 'Clone as New Version')}
            </button>
          </div>

          <div className={styles.controlBlock}>
            <details open={reviews.length > 0}>
              <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: '0.5rem' }}>
                {t('resume.compareVersionsTitle') || 'Version Compare'}
              </summary>
              <label className={styles.selectLabel}>
                {t('resume.compareTarget') || 'Compare with'}
                <select value={compareReviewId} onChange={(e) => setCompareReviewId(e.target.value)}>
                  <option value="">{t('resume.optional') || '—'}</option>
                  {reviews.map((r) => (
                    <option key={r.review_id} value={r.review_id}>
                      {r.review_id.slice(0, 8)}… {r.status ? `(${r.status})` : ''}
                    </option>
                  ))}
                </select>
              </label>
              {!!compareSourceText && (
                <label className={styles.selectLabel}>
                  {t('resume.compareSection') || 'Section'}
                  <select value={compareSection} onChange={(e) => setCompareSection(e.target.value)}>
                    {sectionOptions.map((sec) => (
                      <option key={sec} value={sec}>
                        {sectionLabel(sec)}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <button type="button" className="btn btn-secondary btn-sm" onClick={handleCompare} disabled={!compareReviewId || compareLoading}>
                {compareLoading ? t('common.loading') : (t('resume.runCompare') || 'Compare')}
              </button>
            </details>
            {compareStats && (
              <div className={styles.compareStats}>
                <span>{(t('resume.compareAdded') || 'Added').replace('{n}', String(compareStats.added))}</span>
                <span>{(t('resume.compareRemoved') || 'Removed').replace('{n}', String(compareStats.removed))}</span>
                <span>{(t('resume.compareOverlap') || 'Overlap').replace('{n}', String(compareStats.overlap))}</span>
              </div>
            )}
            {compareDiffRows.length > 0 && (
              <>
                {diffInsights && (
                  <DiffInsightsPanel diffInsights={diffInsights} t={t} />
                )}
                <div className={styles.compareActions}>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={handleLoadComparedVersion}>
                    {t('resume.loadComparedIntoEditor') || 'Load compared version into editor'}
                  </button>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={handleAppendAddedOnly}>
                    {t('resume.appendAddedOnly') || 'Append added lines only'}
                  </button>
                  {compareSection !== 'all' && (
                    <button type="button" className="btn btn-secondary btn-sm" onClick={handleReplaceWithComparedSection}>
                      {t('resume.replaceSectionFromCompared') || 'Replace selected section from compared'}
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setCompareMode((m) => (m === 'changes' ? 'all' : 'changes'))}
                  >
                    {compareMode === 'changes'
                      ? (t('resume.showAllDiffRows') || 'Show all rows')
                      : (t('resume.showChangedOnly') || 'Show changed only')}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleExportReport('docx')}
                    disabled={exportingReport !== null}
                  >
                    {exportingReport === 'docx'
                      ? (t('common.loading') || 'Loading...')
                      : (t('resume.exportExplainReportDocx') || 'Export Explainability DOCX')}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleExportReport('pdf')}
                    disabled={exportingReport !== null}
                  >
                    {exportingReport === 'pdf'
                      ? (t('common.loading') || 'Loading...')
                      : (t('resume.exportExplainReportPdf') || 'Export Explainability PDF')}
                  </button>
                </div>
                <div className={styles.compareDiffGrid}>
                  <div className={styles.compareDiffCol}>
                    <div className={styles.compareDiffHead}>{t('resume.compareBaseVersion') || 'Baseline Version'}</div>
                    <div className={styles.compareDiffBody}>
                      {visibleRows.map((row, idx) => (
                        <div key={`l-${idx}`} className={`${styles.diffLine} ${styles[`diff${row.leftMark[0].toUpperCase()}${row.leftMark.slice(1)}`]}`}>
                          {renderHighlightedLine(row.left, row.leftMark, 'left')}
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className={styles.compareDiffCol}>
                    <div className={styles.compareDiffHead}>{t('resume.compareCurrentVersion') || 'Current Version'}</div>
                    <div className={styles.compareDiffBody}>
                      {visibleRows.map((row, idx) => (
                        <div key={`r-${idx}`} className={`${styles.diffLine} ${styles[`diff${row.rightMark[0].toUpperCase()}${row.rightMark.slice(1)}`]}`}>
                          {renderHighlightedLine(row.right, row.rightMark, 'right')}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
