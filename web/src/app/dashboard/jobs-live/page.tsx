'use client';

import { useEffect, useRef, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { studentBff } from '@/lib/bffClient';
import { DEMO_JOBS_LIVE } from '@/lib/demoDataset';

type Job = {
  posting_id: string;
  source_site: string;
  title: string;
  company?: string;
  location?: string;
  salary?: string;
  source_url: string;
  match_score?: number;
  matched_skills?: string[];
  description?: string;
};

const SOURCE_LABELS: Record<string, string> = {
  jobsdb_hk: 'JobsDB',
  ctgoodjobs_hk: 'CTgoodjobs',
  linkedin: 'LinkedIn',
  hk_indeed: 'Indeed HK',
};

export default function JobsLivePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [q, setQ] = useState('');
  const [source, setSource] = useState('');
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [isDemo, setIsDemo] = useState(false);
  const qRef = useRef(q);
  const srcRef = useRef(source);

  const load = async (keyword = q, src = source) => {
    qRef.current = keyword;
    srcRef.current = src;
    setLoading(true);
    try {
      const data = await studentBff.getJobsLive({
        q: keyword || undefined,
        source_site: src || undefined,
        limit: 60,
      });
      const items = data.items || [];
      if (items.length === 0 && !keyword && !src) {
        setJobs(DEMO_JOBS_LIVE);
        setTotal(DEMO_JOBS_LIVE.length);
        setIsDemo(true);
      } else {
        setJobs(items);
        setTotal(data.count || items.length);
        setIsDemo(false);
      }
    } catch {
      setJobs(DEMO_JOBS_LIVE);
      setTotal(DEMO_JOBS_LIVE.length);
      setIsDemo(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFilter = () => load(q, source);
  const handleClear = () => { setQ(''); setSource(''); load('', ''); };

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1>Live Jobs · Hong Kong</h1>
            <p style={{ margin: 0, color: 'var(--gray-500)' }}>
              {isDemo
                ? 'Sample postings — real job data is being loaded'
                : `${total} real Hong Kong job postings · your skill match shown per listing`}
            </p>
          </div>
        </div>

        {/* Search bar */}
        <div className="card" style={{ marginBottom: '1rem' }}>
          <div className="card-content" style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              className="input"
              placeholder="Search title, company, skill…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleFilter()}
              style={{ maxWidth: 280, flex: '1 1 200px' }}
            />
            <select
              className="input"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              style={{ maxWidth: 180 }}
            >
              <option value="">All sources</option>
              <option value="jobsdb_hk">JobsDB HK</option>
              <option value="ctgoodjobs_hk">CTgoodjobs HK</option>
              <option value="linkedin">LinkedIn</option>
            </select>
            <button className="btn btn-primary btn-sm" onClick={handleFilter}>Search</button>
            {(q || source) && (
              <button className="btn btn-ghost btn-sm" onClick={handleClear}>Clear</button>
            )}
          </div>
        </div>

        {/* Job cards */}
        {loading ? (
          <div className="grid">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="card">
                <div className="card-content">
                  <div className="skeleton" style={{ height: 22, marginBottom: 8 }} />
                  <div className="skeleton" style={{ height: 16, width: '60%', marginBottom: 8 }} />
                  <div className="skeleton" style={{ height: 14, width: '40%' }} />
                </div>
              </div>
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <div className="card">
            <div className="card-content" style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--gray-500)' }}>
              <p style={{ fontSize: 36, margin: 0 }}>🔍</p>
              <p style={{ margin: '0.5rem 0 0', fontWeight: 500 }}>No jobs found</p>
              <p style={{ fontSize: 13, margin: '0.25rem 0 0' }}>Try different keywords or clear the filters.</p>
            </div>
          </div>
        ) : (
          <div className="grid">
            {jobs.map((job) => {
              const matchScore = Math.round(Number(job.match_score || 0));
              const matchColor = matchScore >= 60 ? 'var(--hku-green)' : matchScore >= 30 ? '#f59e0b' : 'var(--gray-400)';
              const sourceLabel = SOURCE_LABELS[job.source_site] || job.source_site;
              return (
                <div key={job.posting_id} className="card">
                  <div className="card-content">
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'flex-start' }}>
                      <h3 style={{ margin: 0, fontSize: '1rem', flex: 1 }}>{job.title}</h3>
                      <span
                        className="badge"
                        style={{ background: matchColor, color: '#fff', whiteSpace: 'nowrap', flexShrink: 0 }}
                      >
                        {matchScore}% match
                      </span>
                    </div>
                    <p style={{ margin: '0.35rem 0 0', color: 'var(--gray-600)', fontSize: 14 }}>
                      <strong>{job.company || 'Unknown company'}</strong>
                      {job.location ? ` · ${job.location}` : ''}
                    </p>
                    {job.salary && (
                      <p style={{ margin: '0.2rem 0 0', color: 'var(--gray-500)', fontSize: 13 }}>
                        💰 {job.salary}
                      </p>
                    )}
                    {(job.matched_skills || []).length > 0 && (
                      <div style={{ margin: '0.4rem 0 0', display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {(job.matched_skills || []).map((s) => (
                          <span
                            key={s}
                            style={{ fontSize: 11, background: 'var(--hku-green-light, #e8f5e9)', color: 'var(--hku-green)', padding: '2px 6px', borderRadius: 4 }}
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                    )}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.6rem' }}>
                      <span style={{ fontSize: 11, color: 'var(--gray-400)' }}>via {sourceLabel}</span>
                      <a
                        className="btn btn-ghost btn-sm"
                        href={job.source_url}
                        target="_blank"
                        rel="noreferrer"
                        style={{ fontSize: 12 }}
                      >
                        View posting →
                      </a>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
