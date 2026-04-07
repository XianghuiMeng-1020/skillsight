'use client';

import { useEffect, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { studentBff } from '@/lib/bffClient';

type NotificationItem = {
  notification_id: string;
  title: string;
  message: string;
  source_url?: string;
  is_read: boolean;
  created_at?: string;
};

export default function NotificationsPage() {
  const [items, setItems] = useState<NotificationItem[]>([]);

  const load = async () => {
    try {
      const data = await studentBff.getNotifications(50);
      setItems(data.items || []);
    } catch {
      setItems([]);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const markRead = async (id: string) => {
    try {
      await studentBff.markNotificationRead(id);
      await load();
    } catch {
      // noop
    }
  };

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1>Notifications</h1>
            <p style={{ margin: 0, color: 'var(--gray-500)' }}>Matched job alerts and system updates.</p>
          </div>
        </div>
        <div className="card">
          <div className="card-content">
            {items.length === 0 ? (
              <p>No notifications yet.</p>
            ) : (
              items.map((n) => (
                <div key={n.notification_id} style={{ borderBottom: '1px solid var(--gray-100)', padding: '0.6rem 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                    <strong>{n.title}</strong>
                    {!n.is_read ? (
                      <button className="btn btn-ghost btn-sm" onClick={() => markRead(n.notification_id)}>Mark read</button>
                    ) : (
                      <span className="badge">Read</span>
                    )}
                  </div>
                  <p style={{ margin: '0.35rem 0' }}>{n.message}</p>
                  {n.source_url ? <a href={n.source_url}>Open</a> : null}
                </div>
              ))
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
