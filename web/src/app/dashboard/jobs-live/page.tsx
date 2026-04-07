'use client';

import { useEffect, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { studentBff } from '@/lib/bffClient';

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
};

export default function JobsLivePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [q, setQ] = useState('');
  const [source, setSource] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const data = await studentBff.getJobsLive({ q: q || undefined, source_site: source || undefined, limit: 50 });
      setJobs(data.items || []);
    } catch {
      setJobs([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1>Live Jobs</h1>
            <p style={{ margin: 0, color: 'var(--gray-500)' }}>Browse imported real job postings and your match score.</p>
          </div>
        </div>
        <div className="card" style={{ marginBottom: '1rem' }}>
          <div className="card-content" style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <input className="input" placeholder="Keyword..." value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 260 }} />
            <input className="input" placeholder="Source site..." value={source} onChange={(e) => setSource(e.target.value)} style={{ maxWidth: 220 }} />
            <button className="btn btn-primary btn-sm" onClick={load}>Filter</button>
          </div>
        </div>
        <div className="grid">
          {loading ? [1, 2, 3, 4].map((i) => <div key={i} className="card"><div className="card-content"><div className="skeleton" style={{ height: 24 }} /></div></div>) : jobs.map((job) => (
            <div key={job.posting_id} className="card">
              <div className="card-content">
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem' }}>
                  <h3 style={{ margin: 0 }}>{job.title}</h3>
                  <span className="badge badge-primary">{Math.round(Number(job.match_score || 0))}% match</span>
                </div>
                <p style={{ margin: '0.35rem 0', color: 'var(--gray-600)' }}>
                  {(job.company || 'Unknown company')} · {(job.location || 'Location N/A')} · {(job.salary || 'Salary N/A')}
                </p>
                {job.matched_skills?.length ? (
                  <p style={{ margin: 0, fontSize: 13, color: 'var(--gray-600)' }}>
                    Matched skills: {job.matched_skills.join(', ')}
                  </p>
                ) : null}
                <a className="btn btn-ghost btn-sm" href={job.source_url} target="_blank" rel="noreferrer" style={{ marginTop: '0.5rem' }}>
                  Open original posting
                </a>
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
