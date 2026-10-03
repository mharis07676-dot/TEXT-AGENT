"use client";

import Link from "next/link";

import { AppShell } from "@/components/AppShell";
import { DataView, useAsyncData } from "@/components/useAsyncData";
import { StatCard } from "@/components/StatCard";
import { ChannelBadge } from "@/components/text-agent/ChannelBadge";
import { api } from "@/lib/api";
import { displayName, formatRelativeTime, maskPhone } from "@/lib/format";

export default function DashboardPage() {
  const { data, error, loading, reload } = useAsyncData(async () => {
    const [stats, conversations] = await Promise.all([
      api.getMessagingStats(),
      api.getConversations({ page_size: 8 }),
    ]);
    return { stats, recent: conversations.items };
  }, []);

  return (
    <AppShell title="Dashboard" subtitle="Operational overview for Synas Labs text agents">
      <DataView
        loading={loading}
        error={error}
        data={data}
        emptyTitle="No messaging data yet."
        emptyDescription="SMS and WhatsApp conversations will appear here once activity starts."
        onRetry={reload}
      >
        {(view) => (
          <div className="space-y-8">
            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Total Conversations" value={view.stats.total_conversations} />
              <StatCard label="Active Conversations" value={view.stats.active_conversations} />
              <StatCard label="Unread" value={view.stats.unread_conversations} />
              <StatCard label="AI Conversations" value={view.stats.ai_conversations} />
              <StatCard label="Human Mode" value={view.stats.human_mode_conversations} />
              <StatCard label="SMS" value={view.stats.sms_conversations} />
              <StatCard label="WhatsApp" value={view.stats.whatsapp_conversations} />
              <StatCard label="Closed" value={view.stats.closed_conversations} />
            </section>

            <section className="rounded-xl border border-moss/10 bg-white p-5 shadow-sm">
              <div className="mb-4 flex items-center justify-between gap-3">
                <h3 className="font-display text-xl font-semibold">Recent conversations</h3>
                <Link href="/text-agent/inbox" className="text-sm font-semibold text-leaf hover:underline">
                  Open inbox
                </Link>
              </div>
              {view.recent.length === 0 ? (
                <p className="text-sm text-moss/60">No conversations yet.</p>
              ) : (
                <ul className="divide-y divide-moss/10">
                  {view.recent.map((conversation) => (
                    <li key={conversation.id}>
                      <Link
                        href={`/text-agent/inbox?c=${conversation.id}`}
                        className="flex items-center justify-between gap-3 py-3 hover:bg-mist/50"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold">
                            {displayName(conversation.contact_name, conversation.contact_phone)}
                          </p>
                          <p className="truncate text-xs text-moss/55">
                            {maskPhone(conversation.contact_phone)} ·{" "}
                            {conversation.latest_message_preview || "No messages"}
                          </p>
                        </div>
                        <div className="flex shrink-0 flex-col items-end gap-1">
                          <ChannelBadge channel={conversation.channel} />
                          <span className="text-[11px] text-moss/50">
                            {formatRelativeTime(
                              conversation.latest_message_at ?? conversation.last_message_at,
                            )}
                          </span>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )}
      </DataView>
    </AppShell>
  );
}
