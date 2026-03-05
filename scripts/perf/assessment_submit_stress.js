import http from 'k6/http';
import { check, sleep } from 'k6';

const API_BASE = __ENV.API_BASE || 'http://127.0.0.1:8001';
const TOKEN = __ENV.TOKEN || '';
const USER_ID = __ENV.USER_ID || 'perf_user';
const TARGET_RPS = Number(__ENV.TARGET_RPS || 100);
const STAGE_SECONDS = Number(__ENV.STAGE_SECONDS || 60);
const ASSESSMENT_TYPE = __ENV.ASSESSMENT_TYPE || 'programming';

const SMOKE = __ENV.SMOKE === '1' || __ENV.SMOKE === 'true';
const effectiveRps = SMOKE ? 10 : TARGET_RPS;
const effectiveDuration = SMOKE ? 15 : STAGE_SECONDS;

export const options = {
  scenarios: {
    constant_rps_submit: {
      executor: 'constant-arrival-rate',
      rate: effectiveRps,
      timeUnit: '1s',
      duration: `${effectiveDuration}s`,
      preAllocatedVUs: Math.max(10, Math.ceil(effectiveRps * 1.5)),
      maxVUs: Math.max(50, effectiveRps * 4),
    },
  },
  thresholds: SMOKE
    ? { http_req_failed: ['rate<0.5'], http_req_duration: ['p(95)<15000'] }
    : { http_req_failed: ['rate<0.05'], http_req_duration: ['p(95)<2500'] },
};

function authHeaders(extra = {}) {
  return {
    'Content-Type': 'application/json',
    ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
    ...extra,
  };
}

function startSession() {
  if (ASSESSMENT_TYPE === 'programming') {
    return http.post(
      `${API_BASE}/interactive/programming/start`,
      JSON.stringify({ user_id: USER_ID, difficulty: 'easy', language: 'python' }),
      { headers: authHeaders() }
    );
  }
  if (ASSESSMENT_TYPE === 'writing') {
    return http.post(
      `${API_BASE}/interactive/writing/start`,
      JSON.stringify({ user_id: USER_ID, time_limit_minutes: 30, min_words: 300, max_words: 500 }),
      { headers: authHeaders() }
    );
  }
  return http.post(
    `${API_BASE}/interactive/communication/start`,
    JSON.stringify({ user_id: USER_ID, duration_seconds: 60, allow_retries: false }),
    { headers: authHeaders() }
  );
}

function submitSession(sessionId, antiCopyToken) {
  const idem = `${ASSESSMENT_TYPE}:${sessionId}`;
  if (ASSESSMENT_TYPE === 'programming') {
    return http.post(
      `${API_BASE}/interactive/programming/submit`,
      JSON.stringify({
        session_id: sessionId,
        code: 'def two_sum(nums, target):\n    return [0, 1]',
        language: 'python',
      }),
      {
        headers: authHeaders({
          'Idempotency-Key': idem,
          'X-Model-Version': 'k6-v1',
          'X-Rubric-Version': 'rubric-v1',
        }),
      }
    );
  }
  if (ASSESSMENT_TYPE === 'writing') {
    return http.post(
      `${API_BASE}/interactive/writing/submit`,
      JSON.stringify({
        session_id: sessionId,
        content: 'this is a stable writing response '.repeat(40),
        anti_copy_token: antiCopyToken || 'demo_token',
        keystroke_data: { chars_per_minute: 180, paste_count: 0 },
      }),
      {
        headers: authHeaders({
          'Idempotency-Key': idem,
          'X-Model-Version': 'k6-v1',
          'X-Rubric-Version': 'rubric-v1',
        }),
      }
    );
  }
  return http.post(
    `${API_BASE}/interactive/communication/submit`,
    JSON.stringify({
      session_id: sessionId,
      transcript: 'This is a stable communication answer for load test.',
      audio_duration_seconds: 40,
    }),
    {
      headers: authHeaders({
        'Idempotency-Key': idem,
        'X-Model-Version': 'k6-v1',
        'X-Rubric-Version': 'rubric-v1',
      }),
    }
  );
}

export default function () {
  const startRes = startSession();
  const okStart = check(startRes, {
    'start status 200': (r) => r.status === 200,
  });
  if (!okStart) {
    sleep(0.2);
    return;
  }

  let startBody;
  try {
    startBody = startRes.json();
  } catch (_) {
    return;
  }
  const sessionId = startBody.session_id;
  const antiCopyToken = startBody.anti_copy_token;
  if (!sessionId) return;

  const submitRes = submitSession(sessionId, antiCopyToken);
  check(submitRes, {
    'submit status 200': (r) => r.status === 200,
    'submit has evaluation': (r) => {
      if (r.status !== 200) return false;
      try {
        const body = r.json();
        return !!(body && body.evaluation);
      } catch (_) {
        return false;
      }
    },
    'submit has skill update marker': (r) => {
      if (r.status !== 200) return false;
      try {
        const body = r.json();
        return !!(body && Object.prototype.hasOwnProperty.call(body, 'skill_update'));
      } catch (_) {
        return false;
      }
    },
  });
}
