import { test, expect, request as playwrightRequest } from '@playwright/test';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

async function getDevToken() {
  const ctx = await playwrightRequest.newContext();
  const resp = await ctx.post(`${API}/auth/dev_login`, {
    data: { subject_id: `stable_user_${Date.now()}`, role: 'student', ttl_s: 3600 },
  });
  if (!resp.ok()) {
    await ctx.dispose();
    return null;
  }
  const data = await resp.json();
  await ctx.dispose();
  return data?.token || null;
}

test.describe('Assessment stability and edge cases', () => {
  test('same programming submission 10 times is stable', async ({ request }) => {
    const health = await request.get(`${API}/health`);
    test.skip(!health.ok(), 'Backend not running; skip stability test.');
    const token = await getDevToken();
    test.skip(!token, 'Cannot obtain dev token; skip stability test.');

    const scores: number[] = [];
    const levels: Array<string | number> = [];

    for (let i = 0; i < 10; i += 1) {
      const startResp = await request.post(`${API}/interactive/programming/start`, {
        headers: { Authorization: `Bearer ${token}` },
        data: { user_id: 'stable_programming_user', difficulty: 'medium', language: 'python' },
      });
      expect(startResp.ok()).toBeTruthy();
      const startData = await startResp.json();

      const submitResp = await request.post(`${API}/interactive/programming/submit`, {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          session_id: startData.session_id,
          code: [
            'def length_of_longest_substring(s):',
            '    seen = {}',
            '    left = 0',
            '    ans = 0',
            '    for right, ch in enumerate(s):',
            '        if ch in seen and seen[ch] >= left:',
            '            left = seen[ch] + 1',
            '        seen[ch] = right',
            '        ans = max(ans, right - left + 1)',
            '    return ans',
          ].join('\n'),
          language: 'python',
        },
      });
      expect(submitResp.ok()).toBeTruthy();
      const submitData = await submitResp.json();
      const ev = submitData.evaluation || {};
      scores.push(Number(ev.score ?? ev.overall_score ?? 0));
      levels.push(ev.level_label ?? ev.level ?? 'unknown');
    }

    expect(scores.length).toBe(10);
    expect(new Set(scores).size).toBe(1);
    expect(new Set(levels).size).toBe(1);
  });

  test('multi-type invalid submissions are handled consistently', async ({ request }) => {
    const health = await request.get(`${API}/health`);
    test.skip(!health.ok(), 'Backend not running; skip edge-case test.');
    const token = await getDevToken();
    test.skip(!token, 'Cannot obtain dev token; skip edge-case test.');

    // 1) Writing: invalid anti_copy_token -> 400
    const startWriting = await request.post(`${API}/interactive/writing/start`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { user_id: 'edge_user', time_limit_minutes: 30, min_words: 100, max_words: 500 },
    });
    expect(startWriting.ok()).toBeTruthy();
    const writingSession = await startWriting.json();
    const badWriting = await request.post(`${API}/interactive/writing/submit`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        session_id: writingSession.session_id,
        content: 'edge case writing content '.repeat(40),
        anti_copy_token: 'wrong_token',
      },
    });
    expect([400, 422]).toContain(badWriting.status());

    // 2) Programming: non-existent session -> 404
    const badProgramming = await request.post(`${API}/interactive/programming/submit`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { session_id: '00000000-0000-0000-0000-000000000000', code: 'print(1)', language: 'python' },
    });
    expect([404, 422]).toContain(badProgramming.status());

    // 3) Communication: exceed max attempts -> final call should be 400
    const startComm = await request.post(`${API}/interactive/communication/start`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { user_id: 'edge_user', duration_seconds: 60, allow_retries: true, max_retries: 1 },
    });
    expect(startComm.ok()).toBeTruthy();
    const commSession = await startComm.json();
    const payload = {
      session_id: commSession.session_id,
      transcript: 'test response for retries',
      audio_duration_seconds: 30,
    };
    const first = await request.post(`${API}/interactive/communication/submit`, { headers: { Authorization: `Bearer ${token}` }, data: payload });
    const second = await request.post(`${API}/interactive/communication/submit`, { headers: { Authorization: `Bearer ${token}` }, data: payload });
    const third = await request.post(`${API}/interactive/communication/submit`, { headers: { Authorization: `Bearer ${token}` }, data: payload });
    expect(first.ok()).toBeTruthy();
    expect(second.ok()).toBeTruthy();
    expect(third.status()).toBe(400);

    // 4) BFF profile read after valid submit should still work
    if (token) {
      const profileResp = await request.get(`${API}/bff/student/profile`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      expect([200, 404]).toContain(profileResp.status());
    }
  });
});
