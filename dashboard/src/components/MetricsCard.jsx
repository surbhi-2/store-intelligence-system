import React from 'react'
import './MetricsCard.css'

function MetricsCard({ title, value, icon, color, highlight }) {
  return (
    <div 
      className={`metric-card ${highlight ? 'highlight' : ''}`}
      style={{ borderLeftColor: color }}
    >
      <div className="metric-icon">{icon}</div>
      <div className="metric-content">
        <p className="metric-title">{title}</p>
        <p className="metric-value">{value}</p>
      </div>
    </div>
  )
}

export default MetricsCard