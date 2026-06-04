import React from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import './FunnelChart.css'

function FunnelChart({ data }) {
  // Transform stage data into chart format
  const chartData = data.map(stage => ({
    name: stage.stage,
    count: stage.visitor_count,
    dropoff: stage.drop_off_percent
  }))

  return (
    <div className="funnel-chart">
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="name" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip 
            contentStyle={{ backgroundColor: '#f7fafc', border: '1px solid #e2e8f0', borderRadius: '8px' }}
            formatter={(value) => value.toFixed(2)}
          />
          <Legend />
          <Bar dataKey="count" fill="#667eea" radius={[8, 8, 0, 0]} />
          <Bar dataKey="dropoff" fill="#f6ad55" radius={[8, 8, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      
      <div className="funnel-stats">
        {data.map((stage, idx) => (
          <div key={idx} className="stage-row">
            <span className="stage-label">{stage.stage}</span>
            <span className="stage-count">{stage.visitor_count} visitors</span>
            <span className="stage-dropoff">{stage.drop_off_percent.toFixed(1)}% drop-off</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default FunnelChart