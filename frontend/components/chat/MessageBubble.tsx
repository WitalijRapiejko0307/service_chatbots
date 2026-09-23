/** Message bubble component with avatars, media rendering and improved styling. */

import React, { memo } from "react";
import type { Message } from "@/lib/types/message";
import { formatMessageTime } from "@/lib/utils/timeFormat";

/** Render a media attachment based on media_type. */
function MediaAttachment({
  url,
  mediaType,
  isUser,
  displayFilename,
}: {
  url: string;
  mediaType: string | null | undefined;
  isUser: boolean;
  displayFilename?: string | null;
}) {
  const type = mediaType || "document";

  if (type === "image") {
    return (
      <a href={url} target="_blank" rel="noopener noreferrer" className="block">
        <img
          src={url}
          alt="Attachment"
          className="max-w-full max-h-72 rounded-sm my-1 object-contain cursor-pointer hover:opacity-90 transition-opacity"
        />
      </a>
    );
  }

  if (type === "video") {
    return (
      <video
        src={url}
        controls
        className="max-w-full max-h-64 rounded-sm my-1"
      />
    );
  }

  if (type === "audio") {
    return (
      <audio src={url} controls className="w-full my-1" />
    );
  }

  // document / unknown — use provided displayName or extract from URL
  const urlFilename = url.split("/").pop()?.split("?")[0] || "file";
  // If the URL filename looks like a UUID (no spaces, long hex), hide it
  const isUuidFilename = /^[0-9a-f-]{36}\.[a-z]+$/i.test(urlFilename);
  const displayName = isUuidFilename ? (displayFilename || "Document") : (displayFilename || urlFilename);

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className={`flex items-center gap-2 my-1 px-3 py-2 rounded-sm border text-sm underline-offset-2 hover:opacity-80 transition-opacity ${
        isUser
          ? "border-accent-foreground/30 text-accent-foreground"
          : "border-border text-foreground"
      }`}
    >
      <span className="text-base">📎</span>
      <span className="truncate max-w-[200px]">{displayName}</span>
    </a>
  );
}

interface MessageBubbleProps {
  message: Message;
}

const getAvatar = (role: Message["role"]) => {
  switch (role) {
    case "user":   return "👤";
    case "admin":  return "👨‍💼";
    case "agent":  return "🤖";
    default:       return "💬";
  }
};

const getRoleLabel = (role: Message["role"]) => {
  switch (role) {
    case "user":  return "You";
    case "admin": return "Admin";
    case "agent": return "AI Assistant";
    default:      return "Unknown";
  }
};

export const MessageBubble: React.FC<MessageBubbleProps> = memo(({ message }) => {
  const isUser  = message.role === "user";
  const isAdmin = message.role === "admin";
  const isAgent = message.role === "agent";

  const metadataString = (
    key: "media_url" | "media_type" | "media_filename"
  ): string | null => {
    const value = message.metadata?.[key];
    return typeof value === "string" ? value : null;
  };

  // Prefer top-level fields, fall back to metadata
  const mediaUrl = message.media_url ?? metadataString("media_url");
  const mediaType = message.media_type ?? metadataString("media_type");
  const mediaFilename = message.media_filename ?? metadataString("media_filename");

  return (
    <div className={`flex items-start gap-2 mb-4 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-lg ${
          isUser
            ? "bg-accent/20"
            : isAdmin
            ? "bg-muted/20"
            : "bg-surface-hover"
        }`}
        aria-label={getRoleLabel(message.role)}
      >
        {getAvatar(message.role)}
      </div>

      {/* Message content */}
      <div className={`flex flex-col ${isUser ? "items-end" : "items-start"} max-w-[70%]`}>
        {(isAdmin || isAgent) && (
          <span className={`text-xs font-medium mb-1 ${isAdmin ? "text-muted" : "text-foreground"}`}>
            {getRoleLabel(message.role)}
          </span>
        )}

        <div
          className={`rounded-sm px-4 py-2.5 transition-all duration-200 ${
            isUser
              ? "bg-accent text-accent-foreground shadow-sm"
              : isAdmin
              ? "bg-accent/80 text-accent-foreground shadow-sm border border-border-strong"
              : "bg-surface-hover text-foreground border border-border shadow-sm"
          }`}
        >
          {/* Media attachment */}
          {mediaUrl && (
            <MediaAttachment
              url={mediaUrl}
              mediaType={mediaType}
              isUser={isUser || isAdmin}
              displayFilename={mediaFilename}
            />
          )}

          {/* Text content */}
          {message.content && (
            <div className="text-sm whitespace-pre-wrap break-words leading-relaxed">
              {message.content}
            </div>
          )}

          {/* Fallback if both empty */}
          {!message.content && !mediaUrl && (
            <div className="text-sm opacity-50 italic">[empty message]</div>
          )}
        </div>

        <p className={`text-xs mt-1 px-1 ${isUser || isAdmin ? "text-muted" : "text-muted-foreground"}`}>
          {formatMessageTime(message.timestamp)}
        </p>
      </div>
    </div>
  );
});

MessageBubble.displayName = "MessageBubble";
