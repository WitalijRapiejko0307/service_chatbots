# Smoke-test checklist

Run against a local or staging stack. Do not paste tokens into tickets or chat logs.

## API and admin

- [ ] `GET /health` returns `status: healthy`
- [ ] Admin login at `/admin/login` (email/password or OTP)
- [ ] Wizard: create an agent, activate, open **web chat** — agent replies using RAG if a FAQ is uploaded

## Channels page

- [ ] Four connectors visible: Telegram, Viber, Instagram, TikTok (no WhatsApp / VK / MAX)
- [ ] Support matrix table visible below connectors (Yes / Limited / No)
- [ ] Webhook URL copy works after connect (or shows the expected base URL)
- [ ] TikTok shows the pending-access banner when `TIKTOK_MESSAGING_ENABLED=false`
- [ ] Instagram shows **Pending review** when connected but unverified (or `app_review_pending` in metadata)
- [ ] OAuth buttons appear only when `INSTAGRAM_APP_ID` / `TIKTOK_APP_ID` are set; TikTok OAuth stays hidden while messaging is disabled
- [ ] Connect / disconnect / toggle errors show inline (not silent)
- [ ] Tokens are never shown in API responses or the UI after save

## Telegram (AC3)

- [ ] Bind a bot token; inbound DM appears in inbox
- [ ] AI reply returns to Telegram
- [ ] Take over (handoff) silences AI until return-to-AI
- [ ] Replay the **same** Telegram webhook payload → no second user message and no second AI reply

## Viber (AC4)

- [ ] Token + webhook set (needs public HTTPS `APP_URL`)
- [ ] Inbound 1:1 appears in inbox; AI reply; handoff silences AI
- [ ] POST without a valid `X-Viber-Content-Signature` is rejected (HMAC)

## Instagram (AC5)

- [ ] GET webhook verify challenge (`hub.mode=subscribe` + verify token) returns the challenge
- [ ] Professional test-account DM ↔ inbox when App Review / roles allow it

## TikTok (AC6)

- [ ] If API access is granted and `TIKTOK_MESSAGING_ENABLED=true`: inbound ↔ inbox like the others
- [ ] If access is pending: UI stays on Pending access; Telegram / Viber / Instagram stay live

## Hardening

- [ ] `ENVIRONMENT=production` refuses to start without a valid `SECRET_ENCRYPTION_KEY`
- [ ] Logs do not contain bot tokens, OAuth `code`, or access tokens (query strings on `/oauth/` omitted)
- [ ] Viber / Instagram / TikTok `APP_URL` is HTTPS in any environment that receives real webhooks
