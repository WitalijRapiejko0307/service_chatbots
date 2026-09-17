# Partner accounts (Step 0)

Service ChatBot talks to messengers through **your** developer accounts. This repo cannot log into BotFather, Meta, Viber, or TikTok for you. Create the four accounts below, then store tokens only in **gitignored** env files (`backend/.env`, never git).

Public HTTPS (tunnel or staging) is **not** required yet. Webhooks for Viber / Instagram / TikTok need a trusted public URL later (Block D / deploy).

**Do not put real tokens in git.** Use empty placeholders in `*.example` files. Copy them locally with `./scripts/dev-setup.sh`.

Locked channels: Telegram, Viber, Instagram, TikTok.  
Out of scope: WhatsApp, VK, MAX.

---

## Status

Fill this in as you go. Leave tokens out of this file.

| Channel | Account created? | App/bot id | Token stored where | Notes |
|---|---|---|---|---|
| Telegram | | | gitignored `backend/.env` → `TELEGRAM_BOT_TOKEN` | Test bot via BotFather; used later in bindings UI |
| Viber | | | gitignored `backend/.env` → `VIBER_AUTH_TOKEN` | Public Account / bot auth token; webhook needs HTTPS later |
| Instagram | | | gitignored `backend/.env` → `INSTAGRAM_WEBHOOK_VERIFY_TOKEN`, `INSTAGRAM_APP_SECRET` | Meta app + Instagram Messaging; App Review for production |
| TikTok | | | gitignored `backend/.env` → `TIKTOK_APP_ID`, `TIKTOK_APP_SECRET` | Developer app + Business Messaging API access request; not on the critical path |

---

## 1. Telegram — BotFather test bot

1. Open Telegram and start [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, pick a display name and a unique username ending in `bot`.
3. Copy the **HTTP API token**. This is what the bindings UI will paste later.
4. Put it in local `backend/.env` as `TELEGRAM_BOT_TOKEN=` (gitignored).
5. Optional: `/setprivacy` and `/setjoingroups` can wait until the Telegram adapter (step 8).

Webhook URL is set by the app later. Local HTTP is enough for this slice.

**Docs**

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Bots tutorial](https://core.telegram.org/bots/tutorial)
- [BotFather](https://t.me/BotFather)

---

## 2. Viber — Public Account / bot

1. You need an active Viber account on iOS/Android (admin of the bot).
2. Create a bot / Public Account via Viber’s partner flow (commercial terms may apply).
3. Copy the **authentication token** (also called application key):  
   Viber → More → Settings → Bots → Edit Info → Your app key, or the Viber Admin Panel.
4. Put it in local `backend/.env` as `VIBER_AUTH_TOKEN=` (gitignored).
5. Do **not** call `set_webhook` until you have a trusted public HTTPS URL (no self-signed certs). That comes with a tunnel or staging, not this slice.

**Docs**

- [Viber REST Bot API](https://developers.viber.com/docs/api/rest-bot-api/)
- [Viber Developers Hub](https://developers.viber.com/docs/all/)
- [Create a bot (partners)](https://partners.viber.com/)

---

## 3. Meta — Instagram Messaging

1. Create a [Meta Developer](https://developers.facebook.com/) account and an **app**.
2. Add **Instagram** / **Messenger** products so the app can use Instagram Messaging (Professional account for testing).
3. In Webhooks, set a **Verify Token** you invent (any strong random string). Match it in `INSTAGRAM_WEBHOOK_VERIFY_TOKEN`.
4. Copy **App Secret** from App Settings → Basic into `INSTAGRAM_APP_SECRET`.
5. App IDs can go in `INSTAGRAM_APP_ID` (optional until OAuth).
6. **Production** DMs to other businesses require [App Review](https://developers.facebook.com/docs/app-review) / Advanced Access. Start that when you have a working test Professional account; it is not a blocker for local `/health`.
7. Callback URL needs public HTTPS later. Leave webhooks unset until then.

**Docs**

- [Instagram Messaging](https://developers.facebook.com/docs/messenger-platform/instagram)
- [Instagram API with Instagram Login — Messaging](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api)
- [App Review](https://developers.facebook.com/docs/app-review)
- [Meta for Developers](https://developers.facebook.com/)

---

## 4. TikTok — developer app + Messaging API access

1. Register at [TikTok for Developers](https://developers.tiktok.com/) and create an app.
2. Note **App ID** and **App Secret** → `TIKTOK_APP_ID`, `TIKTOK_APP_SECRET`.
3. Request access to the **Business Messaging API** (data/privacy review may be required). Approval can take weeks and is region-limited (Open Beta: APAC, LATAM, METAP, North America excluding US; EEA/UK/US inbound is restricted).
4. This is **not on the critical path**. Telegram + Viber + Instagram test mode can ship first. If access is denied, the product can show “pending partner” later.

Webhook / OAuth redirect URLs need public HTTPS later.

**Docs**

- [TikTok for Developers](https://developers.tiktok.com/)
- [Business Messaging API](https://business-api.tiktok.com/portal/docs/business-messaging-api/v1.3)
- [Business Messaging API reference](https://business-api.tiktok.com/portal/docs/business-messaging/v1.3)
- [TikTok API for Business overview](https://business-api.tiktok.com/portal/docs?id=1701890914536450)

---

## Where secrets live

| File | Tracked in git? | Purpose |
|---|---|---|
| `backend/.env.example`, `.env.example` | Yes — empty placeholders only | Contract for local/Docker env |
| `backend/.env` | **No** (gitignored) | Real tokens, JWT, encryption key |
| This markdown file | Yes | Checklist and ids **without** secrets |

If a token leaks into a commit, rotate it in the partner console and treat the old value as compromised.
