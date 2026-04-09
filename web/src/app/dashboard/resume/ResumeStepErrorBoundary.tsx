'use client';

import { Component, type ReactNode } from 'react';
import styles from './resume.module.css';

interface Props {
  children: ReactNode;
  fallbackLabel?: string;
  retryLabel?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ResumeStepErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Resume step error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className={styles.stepContent} style={{ padding: '1.5rem' }}>
          <p style={{ color: 'var(--error)', marginBottom: '0.5rem' }}>
            {(this.state.error && this.state.error.message) || this.props.fallbackLabel || 'Something went wrong'}
          </p>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            {this.props.retryLabel || 'Retry'}
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
