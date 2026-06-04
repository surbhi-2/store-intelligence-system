import React from 'react'
import './AnomaliesPanel.css'

function AnomaliesPanel({ anomalies }) {
  if (!anomalies || anomalies.length === 0) {
    return (
      <div className="anomalies-empty">
        ✅ No anomalies detected! Store is operating normally.
      </div>
    )
  }

  return (
    <div className="anomalies-list">
      {anomalies.map((anomaly, idx) => (
        <div key={idx} className={`anomaly-item severity-${anomaly.severity.toLowerCase()}`}>
          <div className="anomaly-icon">
            {anomaly.severity === 'CRITICAL' && '🔴'}
            {anomaly.severity === 'WARN' && '🟡'}
            {anomaly.severity === 'INFO' && '🔵'}
          </div>
          <div className="anomaly-content">
            <div className="anomaly-type">{anomaly.anomaly_type}</div>
            <div className="anomaly-message">{anomaly.message}</div>
            <div className="anomaly-action">💡 {anomaly.suggested_action}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

export default AnomaliesPanel