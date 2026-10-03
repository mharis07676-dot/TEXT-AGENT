"use client";

import { useEffect, useRef } from "react";

import { EmptyState } from "@/components/EmptyState";
import { LoadingState } from "@/components/LoadingState";
import { MessageBubble } from "@/components/text-agent/MessageBubble";
import type { Message } from "@/lib/types";

export function MessageList({
  messages,
  loading,
  hasMore,
  loadingOlder,
  onLoadOlder,
}: {
  messages: Message[];
  loading: boolean;
  hasMore: boolean;
  loadingOlder?: boolean;
  onLoadOlder?: () => void;
}) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, loading]);

  if (loading) {
    return <LoadingState label="Loading messages…" />;
  }

  if (messages.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <EmptyState
          title="No messages in this conversation yet."
          description="Messages will appear here once the customer or agent replies."
        />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto bg-mist/40 px-4 py-4">
      {hasMore ? (
        <div className="mb-3 flex justify-center">
          <button
            type="button"
            onClick={onLoadOlder}
            disabled={loadingOlder}
            className="rounded-md border border-moss/15 bg-white px-3 py-1.5 text-xs font-semibold text-moss hover:bg-sand disabled:opacity-60"
          >
            {loadingOlder ? "Loading…" : "Load older messages"}
          </button>
        </div>
      ) : null}
      <div className="space-y-3">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
      </div>
      <div ref={bottomRef} />
    </div>
  );
}
