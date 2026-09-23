/** Main chat window component with welcome message and improved error display. */

"use client";

import React from "react";
import { useChat } from "@/lib/hooks/useChat";
import { MessageList } from "./MessageList";
import { MessageInput } from "./MessageInput";
import { TypingIndicator } from "./TypingIndicator";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { EmptyState } from "@/components/shared/EmptyState";

interface ChatWindowProps {
  conversationId: string;
  agentName?: string;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({
  conversationId,
  agentName,
}) => {
  const {
    messages,
    isLoading,
    error,
    handoffNotice,
    isTyping,
    isConnected,
    quickReplies,
    sendMessage,
    messagesEndRef,
  } = useChat(conversationId);

  if (isLoading && messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Connection status */}
      <div className="border-b border-border px-4 py-2.5 bg-surface">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full transition-colors duration-200 ${
                isConnected ? "bg-success" : "bg-danger"
              }`}
              aria-label={isConnected ? "Connected" : "Disconnected"}
            />
            <span className="text-sm text-muted">
              {isConnected ? "Connected" : "Disconnected"}
            </span>
          </div>
          {agentName && (
            <span className="text-xs text-muted-foreground">Chatting with {agentName}</span>
          )}
        </div>
      </div>

      {/* Handoff / human takeover — not a transport failure */}
      {handoffNotice && (
        <div
          className="bg-warning/10 border-l-4 border-warning p-4 m-4 rounded-sm"
          role="status"
        >
          <div className="flex items-start gap-2">
            <span className="text-warning" aria-hidden="true">
              👤
            </span>
            <div>
              <p className="text-sm font-medium text-foreground">Transferred to a human</p>
              <p className="text-sm text-muted mt-1">{handoffNotice}</p>
            </div>
          </div>
        </div>
      )}

      {/* Connection / send errors */}
      {error && (
        <div
          className="bg-danger/10 border-l-4 border-danger p-4 m-4 rounded-sm"
          role="alert"
        >
          <div className="flex items-start gap-2">
            <span className="text-danger" aria-hidden="true">
              ⚠️
            </span>
            <div>
              <p className="text-sm font-medium text-foreground">Connection Error</p>
              <p className="text-sm text-muted mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Messages */}
      {messages.length === 0 && !isLoading ? (
        <EmptyState
          icon="💬"
          title="Start the conversation"
          description={
            agentName
              ? `Send a message to ${agentName} to get started.`
              : "Send a message to get started."
          }
        />
      ) : (
        <MessageList messages={messages} messagesEndRef={messagesEndRef} />
      )}

      {/* Typing indicator */}
      <TypingIndicator isTyping={isTyping} agentName={agentName} />

      {/* Quick-reply chips */}
      {quickReplies.length > 0 && (
        <div className="px-4 pb-2 flex flex-wrap gap-2">
          {quickReplies.map((label) => (
            <button
              key={label}
              onClick={() => void sendMessage({ content: label })}
              className="px-3 py-1.5 text-sm rounded-full border border-border bg-surface hover:bg-surface-hover text-foreground transition-colors"
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <MessageInput
        onSend={(payload) => void sendMessage(payload)}
        disabled={isLoading}
        conversationId={conversationId}
        placeholder={
          agentName
            ? `Type your message to ${agentName}...`
            : "Type your message..."
        }
      />
    </div>
  );
};

