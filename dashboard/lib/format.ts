import type { MessagingChannel, MessageRole } from "./types";

export function formatPhone(value: string | null | undefined): string {
  return value?.trim() || "—";
}

export function maskPhone(value: string | null | undefined): string {
  if (!value) return "—";
  const digits = value.replace(/\D/g, "");
  if (digits.length <= 4) return "****";
  return `${value.slice(0, 3)}***${value.slice(-2)}`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function formatRelativeTime(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const diffMs = Date.now() - date.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return date.toLocaleDateString();
}

export function channelLabel(channel: MessagingChannel): string {
  if (channel === "whatsapp") return "WhatsApp";
  if (channel === "sms") return "SMS";
  const _exhaustive: never = channel;
  return _exhaustive;
}

export function senderLabel(role: MessageRole): string {
  switch (role) {
    case "user":
      return "Customer";
    case "assistant":
      return "AI";
    case "human":
      return "You";
    case "system":
      return "System";
    default: {
      const _exhaustive: never = role;
      return _exhaustive;
    }
  }
}

export function deliveryLabel(status: string | null | undefined): string | null {
  if (!status) return null;
  const normalized = status.toLowerCase();
  if (["queued", "accepted", "sending"].includes(normalized)) return "Sending";
  if (["sent"].includes(normalized)) return "Sent";
  if (["delivered", "read"].includes(normalized)) return "Delivered";
  if (["failed", "undelivered"].includes(normalized)) return "Failed";
  return status;
}

export function statusTone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  const value = status.toLowerCase();
  if (["active", "delivered", "sent", "connected", "configured", "success"].includes(value)) {
    return "success";
  }
  if (["failed", "undelivered", "closed", "error", "not configured"].includes(value)) {
    return "danger";
  }
  if (["queued", "sending", "pending", "archived", "human"].includes(value)) {
    return "warning";
  }
  if (["whatsapp", "sms", "ai", "info"].includes(value)) {
    return "info";
  }
  return "neutral";
}

export function displayName(name: string | null | undefined, phone: string | null | undefined): string {
  if (name?.trim()) return name.trim();
  return formatPhone(phone);
}

export function smsCharCount(text: string): { chars: number; segments: number } {
  const chars = text.length;
  const segments = chars === 0 ? 0 : Math.ceil(chars / 160);
  return { chars, segments };
}
