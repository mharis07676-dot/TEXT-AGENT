export type UserRole = "owner" | "admin" | "agent" | "viewer";

export type MessagingChannel = "sms" | "whatsapp";
export type ConversationStatus = "active" | "closed" | "archived";
export type MessageRole = "user" | "assistant" | "human" | "system";
export type MessageDirection = "inbound" | "outbound";
export type PreferredLanguage = "english" | "roman_urdu" | "urdu" | "unknown";
export type ConversationFilter =
  | "all"
  | "unread"
  | "sms"
  | "whatsapp"
  | "ai_active"
  | "human_mode"
  | "closed";

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface LoginPayload {
  email: string;
  password: string;
  tenant_slug: string;
}

export interface User {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at?: string | null;
}

export interface Conversation {
  id: string;
  contact_id: string;
  channel: MessagingChannel;
  status: ConversationStatus;
  ai_enabled: boolean;
  assigned_user_id?: string | null;
  last_message_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  preferred_language?: PreferredLanguage | null;
  latest_message_preview?: string | null;
  latest_message_at?: string | null;
  unread_count: number;
  metadata?: Record<string, unknown>;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: MessageRole;
  direction: MessageDirection;
  channel: MessagingChannel;
  body: string;
  provider_status?: string | null;
  provider_message_sid?: string | null;
  created_at?: string | null;
  optimistic?: boolean;
  failed?: boolean;
  streaming?: boolean;
}

export interface Contact {
  id: string;
  phone_number: string;
  name?: string | null;
  preferred_language: PreferredLanguage;
  created_at?: string | null;
  updated_at?: string | null;
  last_channel?: MessagingChannel | null;
  last_activity_at?: string | null;
  open_conversation_id?: string | null;
  open_conversation_status?: ConversationStatus | null;
  metadata?: {
    notes?: string;
    tags?: string[];
    lead_status?: string;
  };
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface MessageList {
  items: Message[];
  has_more: boolean;
  next_before?: string | null;
}

export interface MessagingHealth {
  status: string;
  twilio_configured: boolean;
  sms_configured: boolean;
  whatsapp_configured: boolean;
  openai_configured: boolean;
}

export interface MessagingStats {
  total_conversations: number;
  active_conversations: number;
  unread_conversations: number;
  ai_conversations: number;
  human_mode_conversations: number;
  sms_conversations: number;
  whatsapp_conversations: number;
  closed_conversations: number;
}

export interface MessagingAnalytics {
  conversations_by_channel: Array<{ name: string; value: number }>;
  conversations_by_mode: Array<{ name: string; value: number }>;
  conversations_by_status: Array<{ name: string; value: number }>;
  messages_by_day: Array<{ date: string; count: number }>;
  delivery_status: Array<{ name: string; value: number }>;
  total_messages: number;
  outbound_messages: number;
  inbound_messages: number;
  failed_messages: number;
}

export class ApiError extends Error {
  status: number;
  body: string;

  constructor(status: number, body: string) {
    super(body || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}
