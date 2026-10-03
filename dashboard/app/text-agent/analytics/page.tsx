"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AppShell } from "@/components/AppShell";
import { DataView, useAsyncData } from "@/components/useAsyncData";
import { StatCard } from "@/components/StatCard";
import { api } from "@/lib/api";

const COLORS = ["#3d7a5f", "#c45c26", "#1f3d32", "#64748b", "#0ea5e9", "#e11d48"];

export default function TextAgentAnalyticsPage() {
  const { data, error, loading, reload } = useAsyncData(() => api.getMessagingAnalytics(), []);

  return (
    <AppShell title="Analytics" subtitle="SMS and WhatsApp conversation metrics">
      <DataView
        loading={loading}
        error={error}
        data={data}
        emptyTitle="No analytics yet."
        emptyDescription="Metrics appear after conversations and messages are recorded."
        onRetry={reload}
      >
        {(view) => (
          <div className="space-y-8">
            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Total messages" value={view.total_messages} />
              <StatCard label="Inbound" value={view.inbound_messages} />
              <StatCard label="Outbound" value={view.outbound_messages} />
              <StatCard label="Failed outbound" value={view.failed_messages} />
            </section>

            <section className="grid gap-6 lg:grid-cols-2">
              <div className="rounded-xl border border-moss/10 bg-white p-5 shadow-sm">
                <h3 className="font-display text-xl font-semibold">SMS vs WhatsApp</h3>
                <div className="mt-4 h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={view.conversations_by_channel} dataKey="value" nameKey="name" outerRadius={90}>
                        {view.conversations_by_channel.map((entry, index) => (
                          <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="rounded-xl border border-moss/10 bg-white p-5 shadow-sm">
                <h3 className="font-display text-xl font-semibold">AI vs Human mode</h3>
                <div className="mt-4 h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={view.conversations_by_mode}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" />
                      <YAxis allowDecimals={false} />
                      <Tooltip />
                      <Bar dataKey="value" fill="#3d7a5f" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="rounded-xl border border-moss/10 bg-white p-5 shadow-sm lg:col-span-2">
                <h3 className="font-display text-xl font-semibold">Message volume</h3>
                <div className="mt-4 h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={view.messages_by_day}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis allowDecimals={false} />
                      <Tooltip />
                      <Bar dataKey="count" fill="#1f3d32" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </section>
          </div>
        )}
      </DataView>
    </AppShell>
  );
}
