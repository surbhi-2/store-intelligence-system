import React from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

function DwellTimeChart({ data }) {
  const chartData = Object.entries(data).map(([zone, seconds]) => ({
    zone: zone.replace(/_/g, ' '),
    seconds: parseFloat(seconds)
  }))

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="zone" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} label={{ value: 'Seconds', angle: -90, position: 'insideLeft' }} />
        <Tooltip 
          contentStyle={{ backgroundColor: '#f7fafc', border: '1px solid #e2e8f0', borderRadius: '8px' }}
          formatter={(value) => `${value.toFixed(1)}s`}
        />
        <Bar dataKey="seconds" fill="#48bb78" radius={[8, 8, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export default DwellTimeChart