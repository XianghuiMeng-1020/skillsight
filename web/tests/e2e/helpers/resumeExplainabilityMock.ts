import { Page } from '@playwright/test';

export type ExportCall = { export_format?: string };

type SetupOptions = {
  token?: string;
  userId?: string;
  userName?: string;
};

export async function setupResumeExplainabilityMocks(
  page: Page,
  options?: SetupOptions
): Promise<{ exportCalls: ExportCall[] }> {
  const token = options?.token ?? 'e2e-token';
  const userId = options?.userId ?? 'e2e-student';
  const userName = options?.userName ?? 'E2E Student';
  const exportCalls: ExportCall[] = [];

  await page.addInitScript(
    ({ tk, uid, uname }) => {
      localStorage.setItem('skillsight_token', tk);
      localStorage.setItem('skillsight_role', 'student');
      // backward-compat keys for older hooks/pages
      localStorage.setItem('token', tk);
      localStorage.setItem('user', JSON.stringify({ id: uid, role: 'student', name: uname }));
    },
    { tk: token, uid: userId, uname: userName }
  );

  await page.route('**/bff/student/**', async (route) => {
    const req = route.request();
    const url = req.url();
    const method = req.method();

    const json = (body: unknown) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });

    if (url.includes('/bff/student/resume-reviews?')) {
      return json({
        reviews: [
          { review_id: 'rid-current', status: 'completed', total_initial: 66, total_final: 79 },
          { review_id: 'rid-compare', status: 'completed', total_initial: 62, total_final: 73 },
        ],
        total: 2,
      });
    }

    if (url.includes('/bff/student/resume-templates')) {
      return json({
        templates: [
          {
            template_id: 'professional_classic',
            name: 'Professional Classic',
            description: 'test',
            preview_url: '/resume-templates/professional_classic.png',
            recommended: true,
            recommend_score: 90,
          },
        ],
      });
    }

    if (url.includes('/resume-review/rid-current/state')) {
      return json({ review_id: 'rid-current', status: 'completed', max_step: 5, has_initial_scores: true, has_final_scores: true });
    }

    if (url.includes('/resume-review/rid-current/compression-hints')) {
      return json({
        review_id: 'rid-current',
        estimated_pages: 1,
        hints: ['Density looks healthy.'],
      });
    }

    const editableMatch = url.match(/resume-review\/([^/]+)\/editable-resume/);
    if (editableMatch) {
      const rid = editableMatch[1];
      if (rid === 'rid-compare') {
        return json({
          review_id: rid,
          resume_text: [
            'SUMMARY',
            'Built internal tools for operations.',
            'EXPERIENCE',
            '• Improved onboarding process by 15%',
          ].join('\n'),
        });
      }
      return json({
        review_id: rid,
        resume_text: [
          'SUMMARY',
          'Built internal tools for operations and analytics.',
          'EXPERIENCE',
          '• Improved onboarding process by 25%',
          '• Reduced processing time by 30%',
        ].join('\n'),
      });
    }

    if (url.includes('/resume-review/rid-current/diff-insights') && method === 'POST') {
      return json({
        review_id: 'rid-current',
        role_keywords: ['analytics', 'operations'],
        summary: { added_lines: 2, removed_lines: 1, overlap_lines: 2 },
        metrics: { before: {}, after: {} },
        dimension_impact: {
          impact: { delta: 1, signal: 'positive' },
          relevance: { delta: 1, signal: 'positive' },
          structure: { delta: 0, signal: 'neutral' },
          language: { delta: 0, signal: 'neutral' },
          skills_presentation: { delta: 0, signal: 'neutral' },
          ats_friendly: { delta: 1, signal: 'positive' },
        },
        semantic_alignment: {
          avg_similarity: 0.62,
          matched_sentences: 3,
          added_sentences: 2,
          removed_sentences: 1,
          pairs: [],
        },
        risk_validator: { risk_level: 'low', issues: [] },
        attribution: {
          total_delta: 8,
          by_dimension: [
            { dimension: 'impact', score_before: 68, score_after: 76, score_delta: 8, change_signal: 'positive', alignment: 'aligned' },
          ],
        },
        highlights: ['Quantified bullet points increased.'],
        risks: [],
        next_actions: ['Validate with final rubric rescore.'],
      });
    }

    if (url.includes('/resume-review/rid-current/export-attribution-report') && method === 'POST') {
      const body = req.postDataJSON() as { export_format?: string };
      exportCalls.push(body || {});
      const isPdf = body?.export_format === 'pdf';
      return json({
        filename: isPdf ? 'resume_explainability.pdf' : 'resume_explainability.docx',
        content_base64: Buffer.from(isPdf ? 'fake-pdf' : 'fake-docx', 'utf-8').toString('base64'),
        mime_type: isPdf ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        format_used: isPdf ? 'pdf' : 'docx',
      });
    }

    if (url.includes('/bff/student/')) {
      return json({});
    }

    return route.continue();
  });

  return { exportCalls };
}

