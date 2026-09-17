# Service ChatBot — development plan

Copy the full **AI Agents CRM** (Vet-doctor) structure into this workspace as a new product: a web app for service businesses to create AI chatbots and connect them to messengers and social channels.

**Date:** 17 Sep 2026  
**Reference app:** `/home/wentel/CursorProjects/AI Agent CRM/Vet-doctor/AI-Agents-CRM`  
**This workspace:** empty except for this plan. Implementation starts only after confirmation.

---

## Locked decisions

| Item | Value |
|---|---|
| Structure | Full CRM: wizard, workflow canvas, RAG, inbox, handoff, CRM board, questionnaires, stats, audit, web chat for in-app test |
| Domain | Generic service business (FAQ, leads, handoff) — not vet / medical |
| Channels | Telegram, Viber, Instagram, TikTok |
| Out of scope | WhatsApp, VK, MAX, ЮKassa paywall, vet restrictions |
| First live messenger | Telegram (step 8) |
| TikTok | Last; may ship as “pending access” if API approval lags |

---

## Understanding the context

The CRM is a working **operator console** plus **agent runtime**:

- **Frontend:** Next.js admin (agents, inbox, CRM, channels) + web chat
- **Backend:** FastAPI, LangChain agent, RAG, workflow, human handoff
- **Storage:** PostgreSQL + Redis
- **Channels in CRM:** web chat, Telegram, WhatsApp, Instagram, VK, MAX

Service ChatBot reuses that engine. It is **not** a 1:1 clone of the clinic brand or medical domain.

**Buyer:** service business (salon, clinic, school, shop, support) — one bot, four channels, one inbox.  
**End user:** writes in Telegram / Viber / Instagram / TikTok; never sees the builder.

---

## Copy vs write new

| Module | Source | Action |
|---|---|---|
| Stack | Next.js + FastAPI + Postgres + Redis + Docker | Copy layout, new names and env |
| Agent wizard + workflow canvas | 8 steps including LangGraph workflow | Copy; drop medical restriction defaults |
| Inbox + WebSocket handoff | Conversations, take over / return to AI | Copy |
| RAG / knowledge | Folders, chunks, file upload | Copy |
| CRM board, questionnaires, stats, audit | Admin sidebar modules | Copy; restage names for service leads |
| Telegram adapter | `telegram_service` + webhooks + commands | Copy and rebind |
| Instagram adapter | `instagram_service` + Meta webhooks | Copy; start Meta App Review in step 0 |
| Viber adapter | Does not exist in CRM | **New** `ChannelSender` + webhook (Telegram-like) |
| TikTok adapter | Does not exist in CRM | **New** OAuth + Business Messaging API |
| WhatsApp / VK / MAX / ЮKassa | CRM extras | Do not copy |

---

## Architecture

Owner UI never talks to messengers. Every inbound event becomes a conversation message, then the same agent runtime, then `ChannelSender` for that channel.

```
Messenger webhook → adapter → conversation → agent runtime → ChannelSender
Admin (Next.js) ⇄ FastAPI ⇄ Postgres + Redis
Web chat = same runtime, for testing only
```

| Layer | Owns |
|---|---|
| FE — Admin | Login, wizard, channels page, inbox, CRM, RAG, stats, audit |
| FE — Web chat | In-app test of the same agent (not a public product channel) |
| BE — Runtime | AgentConfig JSON, LangChain, RAG, workflow, debounce, timers |
| BE — Channels | telegram / viber / instagram / tiktok webhooks + senders |
| Postgres | agents, bindings, conversations, messages, rag, crm, audit |
| Redis | Reply debounce, workflow timers, auto-steps |

**Shared channel contract (from CRM):** `ChannelBinding` (encrypted token) → inbound webhook → conversation → runtime → `ChannelSender.send_message`.

**Enums:** `telegram`, `viber`, `instagram`, `tiktok`, `web_chat`.

---

## Channels — how the owner connects

| Channel | Owner connects with | Hard part | Build in |
|---|---|---|---|
| Telegram | Bot token from BotFather | Commands, media, quick replies — already in CRM | Step 8 (first live messenger) |
| Viber | Public Account auth token | HTTPS webhook with trusted cert; HMAC signature | Step 9 |
| Instagram | Meta OAuth → Professional account | App Review, 24h window, human handoff required by Meta | Step 10 |
| TikTok | TikTok Login OAuth → Business Account | API access approval, region limits, 48h / 10-message window | Step 11 (last) |

TikTok Business Messaging API is Open Beta (APAC, LATAM, METAP, North America excluding US). EEA / UK / US inbound is restricted. A developer app plus API approval is required before the adapter can be tested for real. Start that application in step 0, in parallel with coding.

---

## Target feature matrix

| Capability | Telegram | Viber | Instagram | TikTok |
|---|---|---|---|---|
| Text in / out | Yes | Yes | Yes | Yes |
| Images | Yes | Yes | Yes | Limited / region |
| Quick replies / buttons | Keyboard | Keyboard / rich | Icebreakers / generic | Up to 3 buttons |
| Proactive first message | Yes | On `conversation_started` | No (user must start) | No (user must start) |
| Response window | None | None | 24 hours | 48 hours, max 10 messages |
| Human handoff | Yes | Yes | Required by Meta | Yes (our inbox) |

---

## Build sequence

Each step is atomic: it can be demoed before the next starts.  
Estimates are **planning guesses**, not tracked hours (~12 weeks total).

| Group | Steps | Est. weeks |
|---|---|---|
| Foundation | 0–1 | 2 |
| Agent platform | 2–4 | 2 |
| Operator desk | 5–7 | 2 |
| Telegram + Viber | 8–9 | 2 |
| Instagram + TikTok | 10–11 | 3 |
| Polish + deploy | 12–15 | 1 |

### Block A — foundation

#### Step 0. Partner accounts

**Build:** Telegram BotFather test bot; Viber bot; Meta app (Instagram Messaging); TikTok developer app + Messaging API access request. Public HTTPS later via tunnel or deploy.

**Done when:** Four developer accounts exist. TikTok request submitted (approval may lag).

**Depends on:** nothing. Runs in parallel with step 1.

#### Step 1. Repo + Docker

**Build:** `backend/`, `frontend/`, `configs/`, `docker-compose` (Postgres 16, Redis 7). FastAPI health, Next.js shell, env examples. No vet brand copy-paste.

**Done when:** `/health` and empty admin page run locally.

**Depends on:** step 0 can run in parallel.

### Block B — platform core (copy CRM)

#### Step 2. Database + auth

**Build:** Migrations from CRM: conversations, messages, agents, bindings, secrets, rag, crm_stages, questionnaires, audit, admin_users. Auth: email/password (not only admin token).

**Done when:** Admin can log in. Schema empty but complete.

**Depends on:** step 1.

#### Step 3. Agent wizard

**Build:** Full 8-step wizard: identity, style, examples, RAG, escalation, LLM, workflow canvas, review. Service defaults (no diagnosis flags).

**Done when:** Create / edit / activate an agent; config stored as JSONB.

**Depends on:** step 2.

#### Step 4. Web chat runtime

**Build:** Port `agent_service`, RAG, escalation, debounce, checkpointer. `/chat/[agentId]` + WebSocket.

**Done when:** Created agent answers in the browser using its knowledge.

**Depends on:** step 3.

### Block C — operator desk (copy CRM)

#### Step 5. Inbox + handoff

**Build:** Conversation list, thread view, take over, return to AI, `NEEDS_HUMAN` badge.

**Done when:** Operator stops the bot and replies as human; AI stays silent until return.

**Depends on:** step 4.

#### Step 6. CRM + questionnaires

**Build:** Kanban stages, lead status on threads, form templates, submissions.

**Done when:** A lead can move across stages; a form can be attached to an agent.

**Depends on:** step 5.

#### Step 7. Knowledge, stats, audit

**Build:** RAG upload UI, stats dashboard, audit log, notifications (e.g. Telegram alert to owner).

**Done when:** FAQ file changes answers. Escalations appear in stats.

**Depends on:** step 5.

### Block D — messengers

#### Step 8. Telegram

**Build:** Copy `telegram_service`, webhook, bot commands, media, quick replies. Bindings UI: paste token, set webhook.

**Done when:** Message in Telegram ↔ same thread in inbox; handoff works.

**Depends on:** step 5.

#### Step 9. Viber

**Build:** New `viber_service`: `set_webhook`, HMAC verify, `send_message`, `conversation_started` welcome. Bindings UI: paste PA token. Requires public HTTPS.

**Done when:** Viber 1:1 chat ↔ inbox. Keyboard/buttons mapped to quick replies where the API allows.

**Depends on:** step 8 (same contract).

#### Step 10. Instagram

**Build:** Copy `instagram_service` + Meta verify token / App Secret HMAC. OAuth connect. 24h window + mandatory human handoff (already in inbox).

**Done when:** IG DM from a test Professional account ↔ inbox. App Review submitted for production users.

**Depends on:** step 8; Meta app from step 0.

#### Step 11. TikTok

**Build:** New `tiktok_service`: OAuth, webhook `im_receive_msg`, send via Business Messaging API. Enforce user-initiated + 48h / 10-message policy. Sandbox until API access is granted.

**Done when:** TikTok DM from an eligible Business Account ↔ inbox. If API access is denied, ship behind a “pending partner” flag — do **not** block Telegram / Viber / Instagram go-live.

**Depends on:** step 8; TikTok approval from step 0.

TikTok is **not** on the critical path.

### Block E — product finish

#### Step 12. Channel bindings UX

**Build:** One Channels page per agent: four connectors, status (active / verified / pending review), webhook URL copy, disconnect.

**Done when:** Owner can connect/disconnect each channel without backend ops.

**Depends on:** step 11 (UI can land earlier with “coming soon” for incomplete adapters).

#### Step 13. Parity pass

**Build:** Media, typing, quick replies, restart command — document per-channel support matrix. Fallback: text-only where the API is weaker (TikTok).

**Done when:** Support matrix is visible in admin. No silent feature that works only on Telegram.

**Depends on:** step 12.

#### Step 14. Hardening

**Build:** Rate limits, secret encryption, webhook idempotency, CORS, i18n RU/EN, empty/error states.

**Done when:** Replay of the same webhook does not double-reply. Tokens never in logs.

**Depends on:** step 12.

#### Step 15. Deploy

**Build:** Compose or Railway-style: API + FastAPI background loops + FE + Postgres + Redis. HTTPS for Viber / Instagram / TikTok webhooks.

**Done when:** Staging URL; all four webhooks reachable; smoke-test checklist green.

**Depends on:** step 14.

---

## Acceptance criteria

| ID | Criterion |
|---|---|
| AC1 | Full CRM structure runs locally: wizard, workflow, RAG, inbox, CRM board, stats |
| AC2 | Agent created in wizard answers in web chat using uploaded FAQ |
| AC3 | Telegram: inbound DM appears in inbox; AI reply returns; handoff silences AI |
| AC4 | Viber: same as AC3 after token + webhook set |
| AC5 | Instagram: same as AC3 for a Professional test account; App Review in flight for public |
| AC6 | TikTok: same as AC3 if API access granted; otherwise UI shows Pending access and other channels stay live |
| AC7 | One conversation identity per user per channel; media stored; no tokens in frontend |
| AC8 | WhatsApp, VK, MAX are absent from UI and enums |

---

## Risks

| Risk | Mitigation |
|---|---|
| TikTok partner gate (weeks, region-blocked) | Not on the critical path. Telegram + Viber + IG test mode can ship first |
| Instagram App Review | Production DMs need Advanced Access. Start Meta app in step 0. Inbox handoff is mandatory |
| Viber HTTPS | No self-signed certs. Local dev needs a trusted tunnel or staging |
| Copying vet domain | Wizard defaults and prompts = service/FAQ, not medical flags. Payments stay out of channel MVP |

---

## Suggested UX for later (not blocking this plan)

The CRM 8-step wizard is copied in step 3. A shorter first-run (identity → knowledge → publish) can wrap that wizard later without changing the data model. One `AgentConfig` JSON remains the source of truth.

---

## Next action

Confirm this file. First coding slice: **step 1** (repo + Docker), while partner accounts from **step 0** are created in parallel.
