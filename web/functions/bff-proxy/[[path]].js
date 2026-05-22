/**
 * Cloudflare Pages Function: BFF passthrough proxy.
 *
 * Why this exists
 * ---------------
 * When the SkillSight frontend talks directly to the Render-hosted FastAPI
 * (`https://skillsight-api.onrender.com/bff/*`), every transient upstream
 * failure that bypasses our FastAPI CORSMiddleware (e.g. Cloudflare's own
 * 524/520 edge errors, a uvicorn worker restart, a 502 from the load
 * balancer) hits the browser without `Access-Control-Allow-Origin`. The
 * browser then surfaces it as the misleading "blocked by CORS policy"
 * message instead of the real "service unavailable", which makes user
 * reports confusing and blocks bffClient's retry path because the network
 * layer can't distinguish a 5xx from a CORS misconfiguration.
 *
 * This proxy fixes that by routing requests through the same origin as the
 * frontend (Cloudflare Pages, which is fronted by CF). Any upstream error
 * still bubbles up, but now it carries CORS headers added by *us*, so the
 * browser exposes the status code to fetch() and our retry logic kicks in.
 *
 * Usage from the frontend
 * -----------------------
 * Set `NEXT_PUBLIC_USE_BFF_PROXY=true` to send `/bff/*` traffic to
 * `/bff-proxy/bff/*` on the same origin. This is opt-in so local dev
 * (which talks straight to the FastAPI) is unaffected.
 */

const UPSTREAM = 'https://skillsight-api.onrender.com';

// Hop-by-hop headers per RFC 7230. Stripping them avoids "header is not
// allowed" surprises on either side of the proxy.
const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
  'host',
]);

function pickAllowOrigin(origin) {
  if (!origin) return '*';
  // Mirror the same allow-list the FastAPI app uses so we don't widen the
  // attack surface beyond what's already permitted.
  const allowList = new Set([
    'https://skillsight-230.pages.dev',
    'https://skillsight.pages.dev',
    'http://localhost:3000',
    'http://127.0.0.1:3000',
  ]);
  if (allowList.has(origin)) return origin;
  if (/^https:\/\/[a-z0-9-]+\.skillsight-\d+\.pages\.dev$/.test(origin)) return origin;
  if (/^https:\/\/skillsight-\d+\.pages\.dev$/.test(origin)) return origin;
  return 'null';
}

function corsHeaders(reqOrigin) {
  const origin = pickAllowOrigin(reqOrigin);
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Credentials': 'true',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS, PATCH',
    'Access-Control-Allow-Headers':
      'Authorization, Content-Type, X-Purpose, X-Requested-With, X-Idempotency-Key, X-Model-Version, X-Rubric-Version, Accept, Origin',
    'Access-Control-Max-Age': '3600',
    'Vary': 'Origin',
  };
}

export async function onRequest(context) {
  const { request } = context;
  const reqUrl = new URL(request.url);
  const reqOrigin = request.headers.get('Origin') || '';

  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: corsHeaders(reqOrigin) });
  }

  // Map /bff-proxy/<path> → <UPSTREAM>/<path>
  const pathPrefix = '/bff-proxy';
  let upstreamPath = reqUrl.pathname.startsWith(pathPrefix)
    ? reqUrl.pathname.slice(pathPrefix.length)
    : reqUrl.pathname;
  if (!upstreamPath.startsWith('/')) upstreamPath = '/' + upstreamPath;
  const upstreamUrl = UPSTREAM + upstreamPath + reqUrl.search;

  const fwdHeaders = new Headers();
  for (const [k, v] of request.headers.entries()) {
    if (HOP_BY_HOP.has(k.toLowerCase())) continue;
    fwdHeaders.set(k, v);
  }
  // Override Origin so FastAPI's CORS middleware doesn't reject the
  // server-to-server hop, then preserve the original under a custom header
  // for any backend logic that wants it.
  if (reqOrigin) fwdHeaders.set('X-Forwarded-Origin', reqOrigin);
  fwdHeaders.set('Origin', UPSTREAM);

  let upstreamRes;
  try {
    // 30s budget — long enough to ride out an uvicorn worker recycle,
    // short enough that the user-facing retry layer can still take over.
    upstreamRes = await fetch(upstreamUrl, {
      method: request.method,
      headers: fwdHeaders,
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
      // @ts-expect-error CF-specific knob
      cf: { cacheTtl: 0, cacheEverything: false },
      redirect: 'manual',
    });
  } catch (err) {
    return new Response(
      JSON.stringify({
        detail: 'upstream_unreachable',
        error: String(err && err.message ? err.message : err),
      }),
      {
        status: 502,
        headers: {
          'Content-Type': 'application/json',
          ...corsHeaders(reqOrigin),
        },
      }
    );
  }

  const respHeaders = new Headers();
  for (const [k, v] of upstreamRes.headers.entries()) {
    if (HOP_BY_HOP.has(k.toLowerCase())) continue;
    // Strip any upstream CORS headers — we add our own consistent ones.
    if (k.toLowerCase().startsWith('access-control-')) continue;
    respHeaders.set(k, v);
  }
  for (const [k, v] of Object.entries(corsHeaders(reqOrigin))) {
    respHeaders.set(k, v);
  }

  return new Response(upstreamRes.body, {
    status: upstreamRes.status,
    statusText: upstreamRes.statusText,
    headers: respHeaders,
  });
}
