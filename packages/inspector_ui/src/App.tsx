import { useState, useEffect } from 'react'
import { ErrorBoundary } from 'react-error-boundary'
import { SessionNavigator } from './pages/SessionNavigator'
import { useUIStore } from './stores/uiStore'
import './App.css'

interface HealthResponse {
  name: string
  version: string
}

function ErrorFallback({ error, resetErrorBoundary }: { error: Error; resetErrorBoundary: () => void }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-red-50">
      <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-6">
        <h2 className="text-lg font-semibold text-red-600 mb-2">Something went wrong</h2>
        <pre className="text-sm text-gray-700 bg-gray-100 p-3 rounded overflow-auto">
          {error.message}
        </pre>
        <button
          onClick={resetErrorBoundary}
          className="mt-4 bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700"
        >
          Try again
        </button>
      </div>
    </div>
  )
}

function App() {
  const [version, setVersion] = useState<string | null>(null)
  const [backendConnected, setBackendConnected] = useState(false)
  const { sseConnected, searchQuery, setSearchQuery } = useUIStore()

  // Check backend health on mount
  useEffect(() => {
    fetch('/_inspector/health')
      .then(response => response.json())
      .then((data: HealthResponse) => {
        setVersion(data.version)
        setBackendConnected(true)
      })
      .catch(err => {
        console.error('Backend health check failed:', err)
        setBackendConnected(false)
      })
  }, [])

  return (
    <ErrorBoundary FallbackComponent={ErrorFallback}>
      <div className="h-screen flex flex-col bg-white">
        {/* Header */}
        <header className="bg-gray-900 text-white px-4 py-2 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-semibold">mcp-agent-inspector</h1>
            {version && (
              <span className="text-xs text-gray-400">v{version}</span>
            )}
          </div>
          
          <div className="flex items-center gap-4">
            {/* Search */}
            <input
              type="text"
              placeholder="Search sessions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="px-3 py-1 text-sm rounded bg-gray-800 text-white placeholder-gray-400 border border-gray-700 focus:outline-none focus:border-blue-500"
            />
            
            {/* Connection Status */}
            <div className="flex items-center gap-2 text-xs">
              <span className={`w-2 h-2 rounded-full ${backendConnected ? 'bg-green-500' : 'bg-red-500'}`} />
              <span>{backendConnected ? 'Connected' : 'Disconnected'}</span>
              {sseConnected && (
                <>
                  <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                  <span>Live</span>
                </>
              )}
            </div>
          </div>
        </header>
        
        {/* Main Content */}
        <main className="flex-1 overflow-hidden">
          {backendConnected ? (
            <SessionNavigator />
          ) : (
            <div className="h-full flex items-center justify-center text-gray-500">
              <div className="text-center">
                <p className="text-lg mb-2">Connecting to Inspector backend...</p>
                <p className="text-sm">Make sure the backend is running on port 7800</p>
              </div>
            </div>
          )}
        </main>
      </div>
    </ErrorBoundary>
  )
}

export default App
