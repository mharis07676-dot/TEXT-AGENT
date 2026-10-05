"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { LoadingState } from "@/components/LoadingState";
import { MessageBubble } from "@/components/text-agent/MessageBubble";
import type { Message } from "@/lib/types";

const NEAR_BOTTOM_PX = 120;

export function MessageList({
  messages,
  loading,
  hasMore,
  loadingOlder,
  onLoadOlder,
  aiTyping = false,
}: {
  messages: Message[];
  loading: boolean;
  hasMore: boolean;
  loadingOlder?: boolean;
  onLoadOlder?: () => void;
  aiTyping?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef(true);
  const [showJump, setShowJump] = useState(false);

  const onScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    const nearBottom = distance < NEAR_BOTTOM_PX;
    stickToBottomRef.current = nearBottom;
    setShowJump(!nearBottom);
  }, []);

  useEffect(() => {
    if (!stickToBottomRef.current) {
      setShowJump(true);
      return;
    }
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    setShowJump(false);
  }, [messages, loading, aiTyping]);

  if (loading) {
    return <LoadingState label="Loading messages…" />;
  }

  if (messages.length === 0 && !aiTyping) {
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
    <div className="relative flex h-full min-h-0 flex-col">
      <div
        ref={containerRef}
        onScroll={onScroll}
        className="flex h-full min-h-0 flex-col overflow-y-auto bg-mist/40 px-4 py-4"
      >
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
        {aiTyping && !messages.some((m) => m.streaming) ? (
          <div className="mt-3 text-xs font-medium text-moss/70" role="status">
            AI is typing…
          </div>
        ) : null}
        <div ref={bottomRef} />
      </div>
      {showJump ? (
        <button
          type="button"
          onClick={() => {
            stickToBottomRef.current = true;
            bottomRef.current?.scrollIntoView({ behavior: "smooth" });
            setShowJump(false);
          }}
          className="absolute bottom-3 left-1/2 z-10 -translate-x-1/2 rounded-full border border-moss/20 bg-white px-3 py-1.5 text-xs font-semibold text-moss shadow"
        >
          New message
        </button>
      ) : null}
    </div>
  );
}
