import { Skeleton, SkeletonCard, SkeletonTable } from '@/components/Skeleton';

export default function DashboardLoading() {
  return (
    <div className="app-container">
      <main className="main-content">
        <div className="page-header">
          <Skeleton width="280px" height="2rem" />
          <div style={{ marginTop: '0.5rem' }}><Skeleton width="160px" height="1.25rem" /></div>
        </div>
        <div className="page-content">
          <div className="stats-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
            {[1, 2, 3, 4].map((i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
          <div style={{ marginBottom: '0.75rem' }}><Skeleton width="100%" height="1.5rem" /></div>
          <SkeletonTable rows={4} />
        </div>
      </main>
    </div>
  );
}
