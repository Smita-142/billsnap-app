import React from 'react';
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts';

const money = value => new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
}).format(Number(value) || 0);

function TooltipBox({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return <div className="chart-tooltip"><span>{label}</span><strong>Spend · {money(payload[0].value)}</strong></div>;
}

export function SpendingChart({ data }) {
  return <ResponsiveContainer width="100%" height="100%"><AreaChart data={data} margin={{ top: 10, right: 4, left: -20, bottom: 0 }}><defs><linearGradient id="spendFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a78bfa" stopOpacity={0.28} /><stop offset="95%" stopColor="#a78bfa" stopOpacity={0} /></linearGradient></defs><CartesianGrid stroke="rgba(255,255,255,.055)" vertical={false} /><XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fill: '#778096', fontSize: 11 }} dy={9} /><YAxis axisLine={false} tickLine={false} tick={{ fill: '#778096', fontSize: 10 }} tickFormatter={value => `${value / 1000}k`} /><Tooltip content={<TooltipBox />} cursor={{ stroke: 'rgba(255,255,255,.17)', strokeDasharray: '4 4' }} /><Area type="monotone" dataKey="amount" stroke="#a78bfa" strokeWidth={2.5} fill="url(#spendFill)" dot={false} activeDot={{ r: 5, fill: '#a78bfa', stroke: '#171a24', strokeWidth: 3 }} /></AreaChart></ResponsiveContainer>;
}

export function CategoryChart({ data }) {
  return <ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data} dataKey="amount" nameKey="name" innerRadius="71%" outerRadius="91%" paddingAngle={4} stroke="none" startAngle={90} endAngle={-270}><Cell fill="#a78bfa" /><Cell fill="#67e8f9" /><Cell fill="#fbbf24" /><Cell fill="#34d399" /><Cell fill="#fb7185" /><Cell fill="#64748b" /></Pie><Tooltip formatter={value => money(value)} contentStyle={{ background: '#1b2030', border: '1px solid rgba(255,255,255,.1)', borderRadius: 10, color: '#fff' }} /></PieChart></ResponsiveContainer>;
}

export function InsightsChart({ data }) {
  return <ResponsiveContainer width="100%" height="100%"><AreaChart data={data} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}><defs><linearGradient id="insightFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#67e8f9" stopOpacity={0.22} /><stop offset="95%" stopColor="#67e8f9" stopOpacity={0} /></linearGradient></defs><CartesianGrid stroke="rgba(255,255,255,.055)" vertical={false} /><XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fill: '#778096', fontSize: 11 }} dy={9} /><YAxis axisLine={false} tickLine={false} tick={{ fill: '#778096', fontSize: 10 }} tickFormatter={value => `${value / 1000}k`} /><Tooltip content={<TooltipBox />} /><Area type="monotone" dataKey="amount" stroke="#67e8f9" strokeWidth={2.3} fill="url(#insightFill)" dot={false} activeDot={{ r: 4, fill: '#67e8f9', stroke: '#171a24', strokeWidth: 3 }} /></AreaChart></ResponsiveContainer>;
}

export function MerchantChart({ data }) {
  return <ResponsiveContainer width="100%" height="100%"><BarChart data={data} layout="vertical" margin={{ left: 0, right: 12, top: 2, bottom: 2 }}><CartesianGrid stroke="rgba(255,255,255,.055)" horizontal={false} /><XAxis type="number" hide /><YAxis dataKey="merchant" type="category" axisLine={false} tickLine={false} tick={{ fill: '#a9afbf', fontSize: 11 }} width={74} /><Tooltip content={<TooltipBox />} cursor={{ fill: 'rgba(255,255,255,.025)' }} /><Bar dataKey="amount" fill="#a78bfa" radius={[0, 5, 5, 0]} barSize={13}>{data.map((item, index) => <Cell key={item.merchant} fill={index === 0 ? '#a78bfa' : '#62558c'} />)}</Bar></BarChart></ResponsiveContainer>;
}
