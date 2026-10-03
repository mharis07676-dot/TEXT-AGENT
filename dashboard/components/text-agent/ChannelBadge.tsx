import { channelLabel } from "@/lib/format";
import type { MessagingChannel } from "@/lib/types";

export function ChannelBadge({ channel }: { channel: MessagingChannel }) {
  const isWhatsApp = channel === "whatsapp";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${
        isWhatsApp
          ? "bg-emerald-50 text-emerald-800 ring-emerald-200"
          : "bg-sky-50 text-sky-800 ring-sky-200"
      }`}
      aria-label={`Channel ${channelLabel(channel)}`}
    >
      <span aria-hidden="true">{isWhatsApp ? "WA" : "SMS"}</span>
      {channelLabel(channel)}
    </span>
  );
}
