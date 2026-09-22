"""Chat API endpoints."""

import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field, model_validator

from app.api.exceptions import AgentNotFoundError, ConversationNotFoundError
from app.api.schemas import AgentIDValidator
from app.api.v1.media import MediaUploadResponse, store_chat_media_bytes
from app.dependencies import CommonDependencies
from app.models.agent_config import AgentConfig
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.services.agent_reply_coordinator import cancel_timer_trigger
from app.services.agent_service import create_agent_service
from app.services.channel_sender import get_channel_sender
from app.config import get_settings
from app.services.inbound_message_pipeline import (
    InboundPipelineOptions,
    PipelineOutcome,
    run_agent_reply_pipeline,
)
from app.utils.enum_helpers import get_enum_value
from app.utils.datetime_utils import utc_now, to_utc_iso_string

router = APIRouter()


class CreateConversationRequest(BaseModel, AgentIDValidator):
    """Request to create a conversation."""

    agent_id: str = Field(..., description="Agent ID")


class CreateConversationResponse(BaseModel):
    """Response for created conversation."""

    conversation_id: str
    agent_id: str
    status: str


class CloseConversationResponse(BaseModel):
    """Response after closing a web chat conversation (idempotent)."""

    conversation_id: str
    status: str


class SendMessageRequest(BaseModel):
    """Request to send a message (text and/or image from web chat upload)."""

    content: str = Field(default="", description="Caption / text", max_length=10000)
    media_url: Optional[str] = Field(None, description="Public URL from POST .../media/upload")
    media_type: Optional[str] = Field(None, description="image | video | … (web chat: image only)")
    media_filename: Optional[str] = Field(None, description="Original filename")

    @model_validator(mode="after")
    def validate_has_body_or_media(self) -> "SendMessageRequest":
        text = (self.content or "").strip()
        has_media = bool(self.media_url and self.media_type)
        if not text and not has_media:
            raise ValueError("Message must include text or an image attachment")
        if bool(self.media_url) != bool(self.media_type):
            raise ValueError("media_url and media_type must be sent together")
        if has_media and self.media_type != "image":
            raise ValueError("Web chat supports image attachments only")
        if self.media_url and not self.media_url.startswith(("https://", "http://")):
            raise ValueError("media_url must be an http(s) URL")
        return self


class SendMessageResponse(BaseModel):
    """Response for sent message."""

    message_id: str
    role: str
    content: str
    timestamp: str


@router.post(
    "/conversations",
    response_model=CreateConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    request: CreateConversationRequest,
    deps: CommonDependencies = Depends(),
):
    """Create a new conversation."""
    # Verify agent exists
    agent_data = await deps.db.get_agent(request.agent_id)
    if not agent_data:
        raise AgentNotFoundError(request.agent_id)

    conversation_id = str(uuid.uuid4())
    conversation = Conversation(
        conversation_id=conversation_id,
        agent_id=request.agent_id,
        channel=MessageChannel.WEB_CHAT,  # Web chat is default channel
        status=ConversationStatus.AI_ACTIVE,
        marketing_status=MarketingStatus.NEW,
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    await deps.db.create_conversation(conversation)

    # Handle both enum and string status (from the database)
    status_value = get_enum_value(conversation.status)
    return CreateConversationResponse(
        conversation_id=conversation_id,
        agent_id=request.agent_id,
        status=status_value,
    )


@router.get("/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(
    conversation_id: str,
    deps: CommonDependencies = Depends(),
):
    """Get conversation by ID."""

    conversation = await deps.db.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)
    return conversation


@router.post(
    "/conversations/{conversation_id}/close",
    response_model=CloseConversationResponse,
    status_code=status.HTTP_200_OK,
)
async def close_conversation(
    conversation_id: str,
    deps: CommonDependencies = Depends(),
):
    """Close a web chat conversation (public). Idempotent if already closed."""
    conversation = await deps.db.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    channel_value = get_enum_value(conversation.channel)
    if channel_value != MessageChannel.WEB_CHAT.value:
        raise HTTPException(
            status_code=400,
            detail="Only web_chat conversations can be closed via this endpoint",
        )

    status_value = get_enum_value(conversation.status)
    if status_value == ConversationStatus.CLOSED.value:
        return CloseConversationResponse(
            conversation_id=conversation_id,
            status=ConversationStatus.CLOSED.value,
        )

    await deps.db.update_conversation(
        conversation_id=conversation_id,
        status=ConversationStatus.CLOSED,
        closed_at=utc_now(),
    )
    return CloseConversationResponse(
        conversation_id=conversation_id,
        status=ConversationStatus.CLOSED.value,
    )


@router.post(
    "/conversations/{conversation_id}/voice",
    status_code=status.HTTP_200_OK,
)
async def transcribe_voice_message(
    conversation_id: str,
    file: UploadFile = File(...),
    deps: CommonDependencies = Depends(),
):
    """Transcribe a voice recording captured in the web chat.

    Accepts a raw audio blob (webm, ogg, mp4 …) from MediaRecorder,
    sends it to the STT service, and returns the transcript text.
    The client then places the transcript in the message input and sends
    it as a regular text message — same pipeline as Telegram voice notes.
    """
    conversation = await deps.db.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    status_value = get_enum_value(conversation.status)
    if status_value == ConversationStatus.CLOSED.value:
        raise HTTPException(status_code=400, detail="Conversation is closed")

    audio_bytes = await file.read()
    filename = file.filename or "voice.webm"

    try:
        from app.services.stt_service import STTError, transcribe_bytes
        transcript = await transcribe_bytes(audio_bytes, filename, language="ru")
    except Exception as exc:
        logger.warning("Voice transcription failed for conversation %s: %s", conversation_id, exc)
        raise HTTPException(status_code=500, detail="Transcription failed. Please try again.")

    return {"transcript": transcript}


@router.post(
    "/conversations/{conversation_id}/media/upload",
    response_model=MediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_web_chat_media(
    conversation_id: str,
    file: UploadFile = File(...),
    deps: CommonDependencies = Depends(),
):
    """Upload chat media for a web_chat conversation (no admin token; same CDN as /media/upload)."""
    conversation = await deps.db.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    channel_value = get_enum_value(conversation.channel)
    if channel_value != MessageChannel.WEB_CHAT.value:
        raise HTTPException(
            status_code=400,
            detail="Media upload is only allowed for web chat conversations",
        )

    status_value = get_enum_value(conversation.status)
    if status_value == ConversationStatus.CLOSED.value:
        raise HTTPException(status_code=400, detail="Conversation is closed")

    file_bytes = await file.read()
    filename = file.filename or "upload"
    return store_chat_media_bytes(file_bytes, filename, file.content_type)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    deps: CommonDependencies = Depends(),
):
    """Send a message in a conversation."""

    # Verify conversation exists
    conversation = await deps.db.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    # Check if conversation is active
    # Handle both enum and string status (from the database)
    status_value = get_enum_value(conversation.status)
    if status_value == ConversationStatus.CLOSED.value:
        raise HTTPException(status_code=400, detail="Conversation is closed")

    content_stripped = (request.content or "").strip()

    msg_metadata: dict = {}
    if request.media_url:
        msg_metadata["media_url"] = request.media_url
        msg_metadata["media_type"] = request.media_type
    if request.media_filename:
        msg_metadata["media_filename"] = request.media_filename

    agent_user_message = content_stripped
    # Pass the image URL natively to the LLM (multimodal) rather than
    # converting it to a text description first.
    user_media_url_for_agent: Optional[str] = (
        request.media_url if request.media_type == "image" else None
    )
    logger.info(
        "[vision] send_message: media_type=%r media_url=%r → user_media_url_for_agent=%r",
        request.media_type,
        request.media_url,
        user_media_url_for_agent,
        extra={"conversation_id": conversation_id},
    )

    # Create user message
    message_id = str(uuid.uuid4())
    user_message = Message(
        message_id=message_id,
        conversation_id=conversation_id,
        agent_id=conversation.agent_id,
        role=MessageRole.USER,
        content=content_stripped,
        channel=conversation.channel,
        external_user_id=conversation.external_user_id,
        timestamp=utc_now(),
        metadata=msg_metadata,
        media_url=request.media_url,
        media_type=request.media_type,
    )

    await deps.db.create_message(user_message)

    # Check if conversation is handled by human - don't process with agent
    if status_value in [
        ConversationStatus.NEEDS_HUMAN.value,
        ConversationStatus.HUMAN_ACTIVE.value,
    ]:
        # Return user message without agent processing
        role_value = get_enum_value(user_message.role)
        return SendMessageResponse(
            message_id=message_id,
            role=role_value,
            content=user_message.content,
            timestamp=to_utc_iso_string(user_message.timestamp),
        )

    # Get agent configuration
    agent_data = await deps.db.get_agent(conversation.agent_id)
    if not agent_data or "config" not in agent_data:
        raise HTTPException(status_code=404, detail="Agent not found or invalid configuration")

    agent_config = AgentConfig.from_dict(agent_data["config"])

    # Get channel sender for the conversation's channel
    # Handle both enum and string channel (from the database)
    conversation_channel = get_enum_value(conversation.channel)
    channel_enum = (
        MessageChannel(conversation_channel)
        if isinstance(conversation_channel, str)
        else conversation.channel
    )
    channel_sender = get_channel_sender(channel_enum, deps.db)

    agent_service = create_agent_service(agent_config, deps.db, channel_sender)

    # Cancel any pending inactivity timer — user is actively responding.
    await cancel_timer_trigger(conversation_id)

    pipeline_result = await run_agent_reply_pipeline(
        deps.db,
        conversation,
        agent_user_message=agent_user_message,
        last_user_plain_content=content_stripped,
        agent_service=agent_service,
        user_media_url=user_media_url_for_agent,
        options=InboundPipelineOptions(
            cancel_inactivity_timer=False,
            skip_debounce_for_media=True,
            create_fallback_agent_message=True,
            update_conversation_ai_active=True,
        ),
    )

    role_value = get_enum_value(user_message.role)
    if pipeline_result.outcome in (
        PipelineOutcome.ESCALATED,
        PipelineOutcome.PRE_MODERATION_ESCALATED,
        PipelineOutcome.DEBOUNCE_SCHEDULED,
    ):
        return SendMessageResponse(
            message_id=message_id,
            role=role_value,
            content=user_message.content,
            timestamp=to_utc_iso_string(user_message.timestamp),
        )

    result = pipeline_result.agent_result or {}
    if result.get("agent_message_id"):
        response_timestamp = utc_now()
    else:
        response_timestamp = pipeline_result.agent_message_timestamp or utc_now()

    return SendMessageResponse(
        message_id=pipeline_result.agent_message_id,
        role=get_enum_value(MessageRole.AGENT),
        content=pipeline_result.agent_response,
        timestamp=to_utc_iso_string(response_timestamp),
    )


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of messages"),
    deps: CommonDependencies = Depends(),
):
    """Get messages for a conversation."""

    # Verify conversation exists
    conversation = await deps.db.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    messages = await deps.db.list_messages(conversation_id, limit=limit, reverse=False)
    return messages

