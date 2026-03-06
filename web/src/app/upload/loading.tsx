import { Skeleton } from '@/components/Skeleton';

export default function UploadLoading() {
  return (
    <div className="app-container">
      <main className="main-content" style={{ maxWidth: '720px', margin: '0 auto' }}>
        <div style={{ marginBottom: '1.5rem' }}>
          <Skeleton width="320px" height="2rem" />
          <div style={{ marginTop: '0.5rem' }}><Skeleton width="480px" height="1.25rem" /></div>
        </div>
        <div style={{
          border: '2px dashed var(--gray-200)',
          borderRadius: 'var(--radius-lg)',
          padding: '3rem 2rem',
          marginBottom: '1.5rem',
          background: 'var(--gray-50)',
        }}>
          <div style={{ margin: '0 auto', width: '80%' }}><Skeleton width="100%" height="4rem" /></div>
          <div style={{ margin: '1rem auto 0', width: '60%' }}><Skeleton width="100%" height="1rem" /></div>
        </div>
        <div style={{ marginBottom: '1rem' }}>
          <Skeleton width="100%" height="3rem" />
          <div style={{ marginTop: '0.5rem' }}><Skeleton width="90%" height="1rem" /></div>
        </div>
      </main>
    </div>
  );
}
