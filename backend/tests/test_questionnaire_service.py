"""Unit tests for questionnaire FSM service (Redis + repo mocked)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.questionnaire import (
    QuestionnaireField,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    SubmissionSource,
    SubmissionStatus,
)
from app.services.questionnaire_service import (
    FSM_KEY_PREFIX,
    FsmMode,
    FsmState,
    cancel,
    clear_fsm,
    find_field,
    format_values_for_prompt,
    get_current_values,
    get_template_or_empty,
    load_fsm,
    open_menu,
    save_fsm,
    skip_current,
    start_edit_field,
    start_fill,
    submit_answer,
    switch_to_edit_menu,
    write_workflow_field,
)
from app.utils.datetime_utils import utc_now


class FakeRedis:
    """Minimal JSON key-value store for questionnaire FSM tests."""

    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}

    async def get_json(self, key: str) -> Optional[dict[str, Any]]:
        return self.store.get(key)

    async def set_json(self, key: str, data: dict[str, Any], ttl: int | None = None) -> None:
        self.store[key] = dict(data)

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


class FakeQuestionnaireRepo:
    """In-memory stand-in for postgres_questionnaire repository."""

    def __init__(self) -> None:
        self.templates: dict[str, QuestionnaireTemplate] = {}
        self.submissions: dict[str, QuestionnaireSubmission] = {}
        self.responses: list[dict[str, str]] = []
        self.latest_values: dict[tuple[str, str], dict[str, str]] = {}
        self.cancelled: list[str] = []
        self.completed: list[str] = []

    async def get_template(self, agent_id: str) -> Optional[QuestionnaireTemplate]:
        return self.templates.get(agent_id)

    async def start_submission(
        self,
        *,
        agent_id: str,
        external_user_id: str,
        channel: str = "telegram",
        conversation_id: Optional[str] = None,
        source: SubmissionSource = SubmissionSource.FILL,
    ) -> QuestionnaireSubmission:
        submission_id = str(uuid4())
        sub = QuestionnaireSubmission(
            submission_id=submission_id,
            agent_id=agent_id,
            external_user_id=external_user_id,
            channel=channel,
            conversation_id=conversation_id,
            status=SubmissionStatus.IN_PROGRESS,
            source=source,
            started_at=utc_now(),
        )
        self.submissions[submission_id] = sub
        return sub

    async def append_response(
        self,
        *,
        submission_id: str,
        agent_id: str,
        external_user_id: str,
        field_key: str,
        value: str,
    ) -> None:
        self.responses.append(
            {
                "submission_id": submission_id,
                "agent_id": agent_id,
                "external_user_id": external_user_id,
                "field_key": field_key,
                "value": value,
            }
        )
        key = (agent_id, external_user_id)
        bucket = self.latest_values.setdefault(key, {})
        bucket[field_key] = value

    async def complete_submission(self, submission_id: str) -> None:
        self.completed.append(submission_id)
        sub = self.submissions.get(submission_id)
        if sub:
            sub.status = SubmissionStatus.COMPLETED
            sub.completed_at = datetime.now(timezone.utc)

    async def cancel_submission(self, submission_id: str) -> None:
        self.cancelled.append(submission_id)
        sub = self.submissions.get(submission_id)
        if sub:
            sub.status = SubmissionStatus.CANCELLED

    async def get_latest_values(self, agent_id: str, external_user_id: str) -> dict[str, str]:
        return dict(self.latest_values.get((agent_id, external_user_id), {}))


def _template() -> QuestionnaireTemplate:
    return QuestionnaireTemplate(
        agent_id="agent-1",
        welcome_message="Welcome!",
        completion_message="Thanks, we received your answers.",
        fields=[
            QuestionnaireField(
                key="name",
                label="Full name",
                question="What is your name?",
                required=True,
                order=0,
            ),
            QuestionnaireField(
                key="phone",
                label="Phone",
                question="Your phone number?",
                required=False,
                order=1,
            ),
        ],
    )


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def fake_repo() -> FakeQuestionnaireRepo:
    return FakeQuestionnaireRepo()


@pytest.fixture
def questionnaire_env(fake_redis: FakeRedis, fake_repo: FakeQuestionnaireRepo):
    with (
        patch("app.services.questionnaire_service.get_redis_client", return_value=fake_redis),
        patch("app.services.questionnaire_service.repo", fake_repo),
    ):
        yield fake_redis, fake_repo


@pytest.mark.asyncio
async def test_fsm_save_and_load_roundtrip(questionnaire_env):
    fake_redis, _ = questionnaire_env
    state = FsmState(
        binding_id="bind-1",
        external_user_id="user-1",
        mode=FsmMode.FILL,
        cursor=1,
        submission_id="sub-1",
    )
    await save_fsm(state)

    loaded = await load_fsm("bind-1", "user-1")
    assert loaded is not None
    assert loaded.mode == FsmMode.FILL
    assert loaded.cursor == 1
    assert loaded.submission_id == "sub-1"
    assert f"{FSM_KEY_PREFIX}bind-1:user-1" in fake_redis.store


@pytest.mark.asyncio
async def test_clear_fsm_removes_redis_key(questionnaire_env):
    fake_redis, _ = questionnaire_env
    await save_fsm(
        FsmState(binding_id="b", external_user_id="u", mode=FsmMode.MENU)
    )
    await clear_fsm("b", "u")
    assert await load_fsm("b", "u") is None


@pytest.mark.asyncio
async def test_open_menu_enters_menu_mode(questionnaire_env):
    state = await open_menu("bind-1", "user-1")
    assert state.mode == FsmMode.MENU
    assert state.submission_id is None


@pytest.mark.asyncio
async def test_start_fill_creates_submission_and_fsm(questionnaire_env):
    _, repo = questionnaire_env
    state, submission = await start_fill(
        binding_id="bind-1",
        agent_id="agent-1",
        external_user_id="user-1",
        channel="telegram",
        conversation_id="conv-1",
    )

    assert state.mode == FsmMode.FILL
    assert state.cursor == 0
    assert state.submission_id == submission.submission_id
    assert submission.source == SubmissionSource.FILL
    assert submission.submission_id in repo.submissions


@pytest.mark.asyncio
async def test_submit_answer_advances_to_next_question(questionnaire_env):
    _, repo = questionnaire_env
    state, submission = await start_fill(
        binding_id="bind-1",
        agent_id="agent-1",
        external_user_id="user-1",
    )
    template = _template()

    state, completed = await submit_answer(
        state=state,
        agent_id="agent-1",
        template=template,
        value="Alice",
    )

    assert completed is False
    assert state.cursor == 1
    assert state.mode == FsmMode.FILL
    assert repo.responses[-1]["field_key"] == "name"
    assert repo.responses[-1]["value"] == "Alice"


@pytest.mark.asyncio
async def test_submit_answer_completes_on_last_field(questionnaire_env):
    _, repo = questionnaire_env
    state, submission = await start_fill(
        binding_id="bind-1",
        agent_id="agent-1",
        external_user_id="user-1",
    )
    template = _template()
    state, _ = await submit_answer(
        state=state, agent_id="agent-1", template=template, value="Alice"
    )

    state, completed = await submit_answer(
        state=state, agent_id="agent-1", template=template, value="+971500000000"
    )

    assert completed is True
    assert state.mode == FsmMode.MENU
    assert state.submission_id is None
    assert submission.submission_id in repo.completed
    assert len(repo.responses) == 2


@pytest.mark.asyncio
async def test_submit_answer_rejects_empty_value(questionnaire_env):
    _, repo = questionnaire_env
    state, _ = await start_fill(
        binding_id="bind-1",
        agent_id="agent-1",
        external_user_id="user-1",
    )

    new_state, completed = await submit_answer(
        state=state,
        agent_id="agent-1",
        template=_template(),
        value="   ",
    )

    assert completed is False
    assert new_state.cursor == 0
    assert repo.responses == []


@pytest.mark.asyncio
async def test_skip_optional_field_advances_cursor(questionnaire_env):
    _, repo = questionnaire_env
    state, submission = await start_fill(
        binding_id="bind-1",
        agent_id="agent-1",
        external_user_id="user-1",
    )
    template = _template()
    state, _ = await submit_answer(
        state=state, agent_id="agent-1", template=template, value="Alice"
    )

    state, completed = await skip_current(state=state, template=template)

    assert completed is True
    assert state.mode == FsmMode.MENU
    assert submission.submission_id in repo.completed
    assert not any(r["field_key"] == "phone" for r in repo.responses)


@pytest.mark.asyncio
async def test_skip_required_field_does_not_advance(questionnaire_env):
    state, _ = await start_fill(
        binding_id="bind-1",
        agent_id="agent-1",
        external_user_id="user-1",
    )

    state, completed = await skip_current(state=state, template=_template())

    assert completed is False
    assert state.cursor == 0
    assert state.mode == FsmMode.FILL


@pytest.mark.asyncio
async def test_cancel_clears_fsm_and_cancels_submission(questionnaire_env):
    fake_redis, repo = questionnaire_env
    state, submission = await start_fill(
        binding_id="bind-1",
        agent_id="agent-1",
        external_user_id="user-1",
    )

    result = await cancel(state)

    assert result.mode == FsmMode.IDLE
    assert submission.submission_id in repo.cancelled
    assert await load_fsm("bind-1", "user-1") is None
    assert f"{FSM_KEY_PREFIX}bind-1:user-1" not in fake_redis.store


@pytest.mark.asyncio
async def test_resume_questionnaire_from_saved_fsm(questionnaire_env):
    """FSM in Redis survives without an active agent conversation (/restart isolation)."""
    state, submission = await start_fill(
        binding_id="bind-1",
        agent_id="agent-1",
        external_user_id="user-1",
    )
    state, _ = await submit_answer(
        state=state,
        agent_id="agent-1",
        template=_template(),
        value="Alice",
    )

    resumed = await load_fsm("bind-1", "user-1")

    assert resumed is not None
    assert resumed.mode == FsmMode.FILL
    assert resumed.cursor == 1
    assert resumed.submission_id == submission.submission_id


@pytest.mark.asyncio
async def test_start_edit_field_and_submit_single_answer(questionnaire_env):
    _, repo = questionnaire_env
    menu_state = await open_menu("bind-1", "user-1")

    state, submission = await start_edit_field(
        state=menu_state,
        agent_id="agent-1",
        field_key="phone",
    )
    assert state.mode == FsmMode.EDIT_FIELD
    assert state.pending_field_key == "phone"
    assert submission.source == SubmissionSource.EDIT

    state, completed = await submit_answer(
        state=state,
        agent_id="agent-1",
        template=_template(),
        value="+971511111111",
    )

    assert completed is True
    assert state.mode == FsmMode.EDIT_MENU
    assert submission.submission_id in repo.completed
    assert repo.responses[-1]["field_key"] == "phone"


@pytest.mark.asyncio
async def test_switch_to_edit_menu(questionnaire_env):
    state = FsmState(
        binding_id="bind-1",
        external_user_id="user-1",
        mode=FsmMode.EDIT_FIELD,
        pending_field_key="name",
    )
    await save_fsm(state)

    updated = await switch_to_edit_menu(state)

    assert updated.mode == FsmMode.EDIT_MENU
    assert updated.pending_field_key is None
    loaded = await load_fsm("bind-1", "user-1")
    assert loaded is not None
    assert loaded.mode == FsmMode.EDIT_MENU


@pytest.mark.asyncio
async def test_get_template_or_empty_returns_blank_template(questionnaire_env):
    tpl = await get_template_or_empty("missing-agent")
    assert tpl.agent_id == "missing-agent"
    assert tpl.fields == []


@pytest.mark.asyncio
async def test_get_current_values_reads_repo(questionnaire_env):
    _, repo = questionnaire_env
    repo.latest_values[("agent-1", "user-1")] = {"name": "Bob"}

    values = await get_current_values("agent-1", "user-1")

    assert values == {"name": "Bob"}


def test_find_field_and_format_values_for_prompt():
    template = _template()
    assert find_field(template, "name") is not None
    assert find_field(template, "missing") is None

    rendered = format_values_for_prompt(
        {"name": "Alice", "phone": "+971500000000"},
        template=template,
    )
    assert "- Full name: Alice" in rendered
    assert "- Phone: +971500000000" in rendered
    assert format_values_for_prompt({}) == ""


@pytest.mark.asyncio
async def test_write_workflow_field_persists_without_fsm(questionnaire_env):
    _, repo = questionnaire_env

    await write_workflow_field(
        agent_id="agent-1",
        external_user_id="user-1",
        field_key="name",
        value="Workflow User",
        conversation_id="conv-wf",
    )

    assert len(repo.submissions) == 1
    assert repo.responses[0]["field_key"] == "name"
    assert repo.responses[0]["value"] == "Workflow User"
    assert repo.completed


@pytest.mark.asyncio
async def test_load_fsm_returns_none_on_redis_error(questionnaire_env, fake_redis):
    async def boom_get_json(_key: str):
        raise ConnectionError("redis down")

    fake_redis.get_json = boom_get_json  # type: ignore[method-assign]

    assert await load_fsm("bind-1", "user-1") is None
