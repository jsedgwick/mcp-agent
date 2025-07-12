import { useState, useEffect } from 'react'
import './App.css'

interface HealthResponse {
  name: string
  version: string
}

function App() {
  const [version, setVersion] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/_inspector/health')
      .then(response => response.json())
      .then((data: HealthResponse) => {
        setVersion(data.version)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  return (
    <div className="app">
      <h1>🔍 Inspector Online</h1>
      <div className="status">
        {loading && <p>Connecting to backend...</p>}
        {error && <p className="error">Error: {error}</p>}
        {version && (
          <p className="success">
            Backend version: <strong>{version}</strong>
          </p>
        )}
      </div>
    </div>
  )
}

export default App
