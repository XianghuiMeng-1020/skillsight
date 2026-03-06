import { Skeleton } from '@/components/Skeleton';

export default function AssessLoading() {
  return (
    <div className="app-container">
      <main className="main-content" style={{ maxWidth: '640px', margin: '0 auto' }}>
        <div style={{ marginBottom: '1.5rem' }}>
          <Skeleton width="280px" height="2rem" />
          <div style={{ marginTop: '0.5rem' }}><Skeleton width="400px" height="1rem" /></div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '0.75rem' }}>
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} style={{ padding: '1rem', border: '1px solid var(--gray-200)', borderRadius: 'var(--radius)', background: 'var(--gray-50)' }}>
              <Skeleton width="100%" height="1.25rem" />
              <div style={{ marginTop: '0.5rem' }}><Skeleton width="80%" height="0.875rem" /></div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
