"use client";

import { KeyboardEvent, useState } from "react";

import { ChannelBadge } from "@/components/text-agent/ChannelBadge";
import { smsCharCount } from "@/lib/format";
import type { Conversation } from "@/lib/types";

export function MessageComposer({
  conversation,
  sending,
  onSend,
  error,
}: {
  conversation: Conversation;
  sending: boolean;
  onSend: (body: string) => Promise<void> | void;
  error?: string | null;
}) {
  const [body, setBody] = useState("");
  const closed = conversation.status === "closed" || conversation.status === "archived";
  const trimmed = body.trim();
  const canSend = Boolean(trimmed) && !sending && !closed;
  const smsMeta = conversation.channel === "sms" ? smsCharCount(body) : null;

  async function submit() {
    if (!canSend) return;
    const value = trimmed;
    setBody("");
    await onSend(value);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  }

  return (
    <div className="border-t border-moss/10 bg-white p-3">
      {closed ? (
        <p className="mb-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
          This conversation is {conversation.status}. Reopen it to send messages.
        </p>
      ) : null}
      {error ? (
        <p className="mb-2 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-800" role="alert">
          {error}
        </p>
      ) : null}
      <div className="mb-2 flex items-center justify-between gap-2">
        <ChannelBadge channel={conversation.channel} />
        {smsMeta ? (
          <span className="text-xs text-moss/55">
            {smsMeta.chars} chars · {smsMeta.segments || 0} SMS segment
            {smsMeta.segments === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>
      <div className="flex items-end gap-2">
        <label className="block min-w-0 flex-1">
          <span className="sr-only">Type message</span>
          <textarea
            value={body}
            onChange={(event) => setBody(event.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
            disabled={closed || sending}
            placeholder="Type a message… (Enter to send, Shift+Enter for new line)"
            className="w-full resize-none rounded-md border border-moss/15 px-3 py-2 text-sm disabled:bg-mist"
          />
        </label>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!canSend}
          className="rounded-md bg-moss px-4 py-2 text-sm font-semibold text-white hover:bg-leaf disabled:opacity-50"
        >
          {sending ? "Sending…" : "Send"}
        </button>
      </div>
    </div>
  );
}
