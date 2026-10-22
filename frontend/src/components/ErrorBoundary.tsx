import { t } from '../i18n'
import { Component, ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo)
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-surface p-6">
          <div className="panel p-6 max-w-md w-full text-center">
            <h1 className="text-xl font-semibold mb-2">{t('Something went wrong')}</h1>
            <p className="text-sm text-text-secondary mb-4">{t('An unexpected error occurred. Please refresh the page.')}</p>
            <button className="btn-primary" onClick={() => window.location.reload()}>{t('Refresh')}</button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
