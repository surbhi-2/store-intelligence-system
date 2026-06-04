import React, { useState, useEffect } from 'react'
import axios from 'axios'
import Dashboard from './components/Dashboard'
import './App.css'

function App() {
  const [store, setStore] = useState('ST1008')
  const [metrics, setMetrics] = useState(null)
  const [funnel, setFunnel] = useState(null)
  const [anomalies, setAnomalies] = useState(null)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(new Date())

  const API_BASE_URL = 'http://localhost:8000'

  // Fetch all data
  const fetchData = async () => {
    try {
      setError(null)
      setLoading(true)

      // Fetch in parallel
      const [metricsRes, funnelRes, anomaliesRes, healthRes] = await Promise.allSettled([
        axios.get(`${API_BASE_URL}/stores/${store}/metrics`),
        axios.get(`${API_BASE_URL}/stores/${store}/funnel`),
        axios.get(`${API_BASE_URL}/stores/${store}/anomalies`),
        axios.get(`${API_BASE_URL}/health`)
      ])

      if (metricsRes.status === 'fulfilled') {
        setMetrics(metricsRes.value.data)
      }
      if (funnelRes.status === 'fulfilled') {
        setFunnel(funnelRes.value.data)
      }
      if (anomaliesRes.status === 'fulfilled') {
        setAnomalies(anomaliesRes.value.data)
      }
      if (healthRes.status === 'fulfilled') {
        setHealth(healthRes.value.data)
      }

      setLastUpdate(new Date())
      setLoading(false)
    } catch (err) {
      setError(err.message || 'Failed to fetch data')
      setLoading(false)
    }
  }

  // Fetch on mount and every 5 seconds
  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [store])

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-content">
          <h1>🏪 Store Intelligence Dashboard</h1>
          <p>Real-time CCTV Analytics & POS Correlation</p>
        </div>
        <div className="header-controls">
          <select 
            value={store} 
            onChange={(e) => setStore(e.target.value)}
            className="store-select"
          >
            <option value="ST1008">Brigade Bangalore (ST1008)</option>
            {/* Add more stores as needed */}
          </select>
          <button onClick={fetchData} className="refresh-btn">
            ↻ Refresh
          </button>
          <div className="status-indicator">
            {health?.status === 'ok' ? (
              <span className="status-online">● Online</span>
            ) : (
              <span className="status-offline">● Offline</span>
            )}
            <span className="last-update">
              Updated: {lastUpdate.toLocaleTimeString()}
            </span>
          </div>
        </div>
      </header>

      {error && (
        <div className="error-banner">
          ⚠️ Error: {error}
        </div>
      )}

      {loading && metrics === null ? (
        <div className="loading">
          <div className="spinner"></div>
          <p>Loading dashboard...</p>
        </div>
      ) : (
        <Dashboard 
          metrics={metrics} 
          funnel={funnel} 
          anomalies={anomalies}
          health={health}
        />
      )}
    </div>
  )
}

export default App