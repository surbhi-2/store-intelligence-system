import React from 'react'
import MetricsCard from './MetricsCard'
import FunnelChart from './FunnelChart'
import AnomaliesPanel from './AnomaliesPanel'
import DwellTimeChart from './DwellTimeChart'
import './Dashboard.css'

function Dashboard({ metrics, funnel, anomalies, health }) {
  if (!metrics) {
    return <div className="dashboard-loading">Loading metrics...</div>
  }

  return (
    <div className="dashboard">
      {/* Top Row — Key Metrics */}
      <div className="metrics-grid">
        <MetricsCard
          title="Unique Visitors"
          value={metrics.unique_visitors}
          icon="👥"
          color="#667eea"
        />
        <MetricsCard
          title="Conversion Rate"
          value={`${metrics.conversion_rate.toFixed(1)}%`}
          icon="📈"
          color="#48bb78"
          highlight={metrics.conversion_rate > 30}
        />
        <MetricsCard
          title="Total Revenue"
          value={`₹${metrics.total_revenue.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
          icon="💰"
          color="#ed8936"
        />
        <MetricsCard
          title="Avg Revenue/Visitor"
          value={`₹${metrics.avg_revenue_per_visitor.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
          icon="💳"
          color="#9f7aea"
        />
        <MetricsCard
          title="Queue Depth"
          value={metrics.current_billing_queue_depth}
          icon="⏳"
          color={metrics.current_billing_queue_depth > 5 ? '#f56565' : '#48bb78'}
        />
        <MetricsCard
          title="Abandonment Rate"
          value={`${metrics.abandonment_rate.toFixed(1)}%`}
          icon="🚪"
          color="#f6ad55"
        />
      </div>

      {/* Middle Row — Funnel & Dwell Time */}
      <div className="charts-grid">
        <div className="chart-container">
          <h3>Conversion Funnel</h3>
          {funnel ? (
            <FunnelChart data={funnel.stages} />
          ) : (
            <div className="chart-loading">Loading funnel...</div>
          )}
        </div>

        <div className="chart-container">
          <h3>Average Dwell Time by Zone</h3>
          {metrics.avg_dwell_per_zone && Object.keys(metrics.avg_dwell_per_zone).length > 0 ? (
            <DwellTimeChart data={metrics.avg_dwell_per_zone} />
          ) : (
            <div className="chart-loading">No zone data available</div>
          )}
        </div>
      </div>

      {/* Bottom Row — Anomalies */}
      <div className="anomalies-container">
        <h3>⚠️ Operational Anomalies</h3>
        {anomalies ? (
          <AnomaliesPanel anomalies={anomalies.anomalies} />
        ) : (
          <div className="chart-loading">Loading anomalies...</div>
        )}
      </div>

      {/* Footer — System Status */}
      <footer className="dashboard-footer">
        <div className="footer-content">
          <p>
            📊 API Version: {health?.api_version || 'N/A'} | 
            🗄️ Total Events: {health?.events_ingested_total || 0} | 
            🏪 Active Stores: {health?.stores_active || 0}
          </p>
          <p className="footer-timestamp">Last updated: {new Date().toLocaleTimeString()}</p>
        </div>
      </footer>
    </div>
  )
}

export default Dashboard