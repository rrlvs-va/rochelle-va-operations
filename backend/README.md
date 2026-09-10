# Secure website inquiry endpoint

This folder contains the server-side endpoint that receives website contact forms and creates a new record in the existing Notion **Client Requests Inbox**.

## Current production flow

Website HTML form → Wasmer Edge endpoint → Notion API → Client Requests Inbox

The Notion credential is **not** stored in GitHub or in public HTML.

## Required Wasmer secret

Create a Notion internal integration, give it access to the Client Requests Inbox database, then store its token in Wasmer as:

- `NOTION_TOKEN` — secret; never commit or paste into source code.

Optional environment variable:

- `NOTION_DATA_SOURCE_ID` — defaults to `28ecfe15-bfb1-4265-abbe-c8c3e29a1a31`.

Do not paste the token into a chat, GitHub issue, commit, HTML file, or JavaScript file.

## Enhanced inquiry test flow

The feature branch `feature/inquiry-verification-whatsapp-v2` adds an opt-in test flow:

Website form → Notion record → owner notification email + requester verification email → Notion verification update → optional WhatsApp continuation

The enhanced flow is controlled by `INQUIRY_V2_ENABLED`. Keep it `false` until the email and verification settings below are configured and a test deployment is ready.

Required/optional Wasmer environment variables for the enhanced flow:

- `INQUIRY_V2_ENABLED=false` — feature flag; set to `true` only on the test deployment when ready.
- `BACKEND_ORIGIN=https://rochelle-va-inquiries.wasmer.app` — public origin used to build verification links.
- `INQUIRY_VERIFICATION_SECRET` — secret random value of at least 32 characters used to sign verification links.
- `RESEND_API_KEY` — secret Resend API key used for requester and owner emails.
- `OWNER_NOTIFICATION_EMAILS` — comma-separated owner email recipient(s) for new inquiry alerts.
- `EMAIL_FROM` — sender identity configured in Resend. The example value is `RVS Website <onboarding@resend.dev>`; use a verified sender/domain for production delivery.
- `WHATSAPP_CONTACT_NUMBER` — optional WhatsApp number in international digits-only format. If omitted, verification still works but the WhatsApp continuation button is not shown.

No real secret values belong in this repository. See `backend/.env.example` for variable names only.

### Enhanced flow behavior

When enabled, a valid contact form submission:

1. Creates the inquiry in the Notion Client Requests Inbox.
2. Adds a generated `Reference Code` and sets `Email Verification` to `Pending`.
3. Sends the owner a **New website inquiry** email containing the requester details, message, reference code, and a direct link to the Notion record.
4. Sends the requester a signed verification link that expires after 24 hours.
5. On verification, updates `Email Verification` to `Verified` and records `Verified At` in Notion.
6. If WhatsApp is configured, offers a signed continuation link and marks `WhatsApp Continued` when used.

If `INQUIRY_V2_ENABLED=false`, the enhanced entrypoint passes submissions directly to the existing production inquiry handler.

## Deployment

The normal production backend uses `src.main:app`. The enhanced test branch changes its Anybuild entrypoint to `src.main_v2:app` so the new flow can be exercised without rewriting the current handler.

After deployment, verify:

```text
GET /health
```

A ready existing endpoint returns JSON with `ok: true` and `notion_configured: true`.

Then submit one test inquiry to:

```text
POST /api/inquiry
```

and confirm that a new row appears in the Notion Client Requests Inbox.

For the enhanced test, also confirm that:

- the owner notification email arrives;
- the requester verification email arrives;
- clicking the verification link changes the Notion verification fields;
- the WhatsApp continuation opens the configured number and updates `WhatsApp Continued`.

## Website sources supported

- `homepage` → Website — Homepage
- `about` → Website — About
- `faq` → Website — FAQ
- `service-policies` → Website — Service Policies
- `privacy` → Website — Privacy

All five website forms use the same endpoint.

## Security controls included

- server-side Notion and email-provider credentials only
- strict field allowlists and length limits
- email validation
- source allowlist
- honeypot spam field
- signed, expiring verification/continuation tokens in the enhanced flow
- no storage of visitor IP addresses
- Notion errors and credentials are never returned to public visitors
- no automatic client conversion, portal creation, or access grants

## Notion mapping

The endpoint writes the existing contact fields plus, when the enhanced flow is enabled:

- Reference Code
- Email Verification
- Verified At
- WhatsApp Continued
