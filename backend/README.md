# Secure website inquiry endpoint

This folder contains the server-side endpoint that will receive every website contact form and create a new record in the existing Notion **Client Requests Inbox**.

## Flow

Website HTML form → Wasmer Edge endpoint → Notion API → Client Requests Inbox

The Notion credential is **not** stored in GitHub or in public HTML.

## Required Wasmer secret

Create a Notion internal integration, give it access to the Client Requests Inbox database, then store its token in Wasmer as:

- `NOTION_TOKEN` — secret; never commit or paste into source code.

Optional environment variable:

- `NOTION_DATA_SOURCE_ID` — defaults to `28ecfe15-bfb1-4265-abbe-c8c3e29a1a31`.

Do not paste the token into a chat, GitHub issue, commit, HTML file, or JavaScript file.

Wasmer CLI pattern (run on your own machine after setting the token in your local shell):

```bash
wasmer app secrets create NOTION_TOKEN "$NOTION_TOKEN" --app <owner>/<contact-app> --redeploy
```

The same secret can be added through the Wasmer app dashboard instead.

## Deployment

Deploy this `backend/` directory as a small Python/FastAPI app on Wasmer Edge. The included `Anybuild` file runs:

```text
uvicorn src.main:app --host 0.0.0.0 --port $PORT
```

After deployment, verify:

```text
GET /health
```

A ready endpoint returns JSON with `ok: true` and `notion_configured: true`.

Then submit one test inquiry to:

```text
POST /api/inquiry
```

and confirm that a new row appears in the Notion Client Requests Inbox.

## Website sources supported

- `homepage` → Website — Homepage
- `about` → Website — About
- `faq` → Website — FAQ
- `service-policies` → Website — Service Policies
- `privacy` → Website — Privacy

All five website forms should use this same endpoint once it has been deployed and tested.

## Security controls included

- server-side Notion token only
- strict field allowlists and length limits
- email validation
- source allowlist
- honeypot spam field
- no storage of visitor IP addresses
- Notion errors and credentials are never returned to public visitors
- no automatic client conversion, portal creation, or access grants

## Notion mapping

The endpoint writes:

- Request
- Requester Name
- Requester Email
- Company / Client Name
- Details
- Request Type
- Status = New
- Source
- Phone
- Contact Channels
- Preferred Contact
- Supporting Link

The Notion database has already been prepared with the additional Source/contact fields required by the endpoint.
