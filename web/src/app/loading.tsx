export default function Loading() {
  return (
    <div className="app-container">
      <main className="main-content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div className="loading">
          <span className="spinner" />
          <span style={{ marginLeft: '0.5rem' }}>Loading…</span>
        </div>
      </main>
    </div>
  );
}
