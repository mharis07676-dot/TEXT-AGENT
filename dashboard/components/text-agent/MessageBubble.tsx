import { deliveryLabel, formatTime, senderLabel } from "@/lib/format";
import type { Message } from "@/lib/types";

export function MessageBubble({ message }: { message: Message }) {
  const isCustomer = message.role === "user";
  const isAi = message.role === "assistant";
  const isHuman = message.role === "human";
  const status = deliveryLabel(message.failed ? "failed" : message.provider_status);
  const failed = Boolean(message.failed) || status === "Failed";

  return (
    <div className={`flex ${isCustomer ? "justify-start" : "justify-end"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 shadow-sm ${
          isCustomer
            ? "rounded-bl-md bg-white ring-1 ring-moss/10"
            : isAi
              ? "rounded-br-md bg-leaf text-white"
              : isHuman
                ? "rounded-br-md bg-moss text-white"
                : "rounded-br-md bg-slate-700 text-white"
        }`}
      >
        <div className="mb-1 flex items-center gap-2">
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
              isCustomer ? "bg-mist text-moss" : "bg-white/15 text-white"
            }`}
          >
            {senderLabel(message.role)}
          </span>
          {message.optimistic ? (
            <span className={`text-[10px] ${isCustomer ? "text-moss/50" : "text-white/70"}`}>Sending…</span>
          ) : null}
        </div>
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.body}</p>
        <div
          className={`mt-1.5 flex items-center gap-2 text-[11px] ${
            isCustomer ? "text-moss/50" : "text-white/70"
          }`}
        >
          <span>{formatTime(message.created_at)}</span>
          {!isCustomer && status ? <span>{status}</span> : null}
          {failed ? (
            <span className="font-semibold text-amber-200" role="status">
              Failed to send
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
