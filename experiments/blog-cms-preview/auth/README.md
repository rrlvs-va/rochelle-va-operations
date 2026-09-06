# OAuth prototype for RVS Insights admin

This folder documents the authentication direction for the future private RVS Insights authoring interface. Nothing here is connected to production yet.

## Goal

Protect the real admin/editor behind GitHub authentication instead of inventing a separate site password.

Proposed flow:

1. Open the private admin host.
2. oauth2-proxy redirects to GitHub.
3. GitHub authenticates Rochelle's account (including passkey/2FA as configured on GitHub).
4. oauth2-proxy allows only the GitHub username `rrlvs-va`.
5. A short-lived secure session cookie grants access to the admin editor.
6. Publishing is handled separately with narrowly scoped GitHub write permissions for blog content/media.

## Important security boundary

The current prototype editor under `experiments/blog-cms-preview/admin/` is intentionally public and non-functional. It is safe only because it cannot save, publish, upload, delete, or access secrets.

The production editor must not remain directly reachable as a static public page. Authentication only works if the real editor is served behind the auth gateway or from a separate admin application whose origin is not bypassable.

## Proposed session defaults

- HTTPS-only cookie
- HttpOnly cookie
- SameSite=Lax
- Host-only cookie name (`__Host-rvsva_admin`)
- 1 hour absolute session lifetime
- 15 minute refresh interval
- GitHub username allowlist: `rrlvs-va`

These values are intentionally conservative because the laptop can be physically shared.

## Secrets

Never commit OAuth client secrets or cookie secrets to GitHub. Store them in the deployment platform's environment-variable/secret store.

Expected variables are listed in `.env.example` with blank values only.

## Deployment question still open

`oauth2-proxy` is a server/proxy process. Before production, confirm a hosting/deployment path that can run it (or use an equivalent GitHub OAuth gateway). The existing public Wasmer static site should remain separate from the protected admin application.

## Publishing authorization

Authentication answers "is this Rochelle?". Publishing authorization is a separate concern. The eventual writer should have the minimum repository permissions needed, ideally limited to the blog content/media paths rather than broad site administration.
