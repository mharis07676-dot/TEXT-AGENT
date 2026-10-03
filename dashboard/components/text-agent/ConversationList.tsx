"use client";

import { ConversationFilters } from "@/components/text-agent/ConversationFilters";
import { ConversationListItem } from "@/components/text-agent/ConversationListItem";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import type { Conversation, ConversationFilter } from "@/lib/types";

export function ConversationList({
  conversations,
  selectedId,
  loading,
  error,
  search,
  filter,
  onSearchChange,
  onFilterChange,
  onSelect,
  onRetry,
}: {
  conversations: Conversation[];
  selectedId: string | null;
  loading: boolean;
  error: string | null;
  search: string;
  filter: ConversationFilter;
  onSearchChange: (value: string) => void;
  onFilterChange: (value: ConversationFilter) => void;
  onSelect: (id: string) => void;
  onRetry: () => void;
}) {
  return (
    <section className="flex h-full min-h-0 flex-col border-r border-moss/10 bg-white">
      <div className="space-y-3 border-b border-moss/10 p-3">
        <label className="block">
          <span className="sr-only">Search conversations</span>
          <input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search name, phone, or message"
            className="w-full rounded-md border border-moss/15 px-3 py-2 text-sm"
          />
        </label>
        <ConversationFilters value={filter} onChange={onFilterChange} />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading ? <LoadingState label="Loading conversations…" /> : null}
        {!loading && error ? <ErrorState message={error} onRetry={onRetry} /> : null}
        {!loading && !error && conversations.length === 0 ? (
          <div className="p-3">
            <EmptyState
              title={search || filter !== "all" ? "No conversations match your search." : "No conversations yet."}
              description={
                search || filter !== "all"
                  ? "Try another filter or search term."
                  : "Incoming SMS and WhatsApp messages will appear here."
              }
            />
          </div>
        ) : null}
        {!loading && !error
          ? conversations.map((conversation) => (
              <ConversationListItem
                key={conversation.id}
                conversation={conversation}
                selected={selectedId === conversation.id}
                onSelect={onSelect}
              />
            ))
          : null}
      </div>
    </section>
  );
}
