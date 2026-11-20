# Invitations by email

Administrators invite people to PaceForge on the **Invitations** page (under **Admin** in the
navigation). PaceForge emails the signup link to the person and also shows the link once, so you
can hand it on yourself. This guide covers sending, mail delivery in development and production,
resending, expired and revoked invitations, the rate limit, the mail templates, the security rules
and the admin API.

## Send an invitation

1. Sign in as an administrator with two-factor authentication turned on.
2. Open **Invitations**, enter the email address and press **Send invitation by email**.
3. PaceForge creates the invitation and attempts to send **one** email with the signup link.
4. The page shows the link once, with one of three notices:
   - *The invitation email was sent to …*: the mail system accepted the message.
   - *No mail server is configured; the email was only written to the server log. Send the link
     yourself.*: no mail left the server. Copy the link and send it yourself.
   - *The invitation email could not be delivered to …*: the invitation still exists. Copy the link
     and send it yourself, or resend the invitation later.

The link is shown only once. If you lose it, press **Resend** on the row.

The invitation is valid for `INVITATION_TTL_DAYS` days (7 by default). It works once and only for
the address it was created for.

## Signup links

The signup page accepts `/account/signup#invitation=<token>&email=<encoded-address>`.
The fragment (the part after `#`) stays in the browser when the page is requested.
Encode both values as URL parameters, including `+` as `%2B` and `%` as `%25`.

PaceForge issues fragment links. Older query links
(`/account/signup?invitation=<token>&email=<encoded-address>`) still work.
If both forms occur in a link, the fragment invitation takes precedence.

After reading either form, the signup page replaces the current history entry with
`/account/signup`. The token and address stay in the open form, and the address is read-only.
Reloading that bare URL shows the invitation-only message. Open the original invitation link
again to restart signup.

## Mail delivery

Django sends the mail. The setting `SMTP_HOST` decides where it goes.

| Setup | Where the mail goes | `delivery` | Page notice | `email_sent` | `sent_at` |
| --- | --- | --- | --- | --- | --- |
| Development: `.env.example` points SMTP at Mailpit | Mailpit on `127.0.0.1:1025`. Read it at <http://localhost:8025>. | `sent` when accepted | Email was sent | `true` | Updated |
| Production with SMTP | Your SMTP server, set with `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` and `SMTP_USE_TLS`. | `sent` when accepted | Email was sent | `true` | Updated |
| No SMTP (`SMTP_HOST` empty) | The Django console: the mail is written to the output of the process. In production that is the `backend` container log. | `console` | Only written to the server log; send the link yourself | `false` | Unchanged |
| Network or SMTP error | The mail could not be sent. | `failed` | Email could not be delivered | `false` | Unchanged |

Without SMTP, nothing leaves the server. The page reports that the email was only written to the
server log. Copy the link on the page and send it yourself. Console output does not update **Last sent**.
A `sent` result means the mail system accepted the message; it does not confirm inbox delivery.

Mailpit runs with the development services:

```sh
docker compose -f compose.dev.yaml up -d db mailpit
```

**When delivery fails.** If the mail server cannot be reached, or it refuses the mail (a network
error, a timeout or an SMTP error), PaceForge:

- logs an error with the invitation id and the type of the error, never the address, the token or
  the link,
- keeps the invitation, and returns `delivery: "failed"` and `email_sent: false`,
- leaves `sent_at` as it was, so the table shows *Not sent* for a new invitation,
- still returns the link, so the administrator is not blocked by a short outage.

## Mail templates

Both templates are in `backend/templates/accounts/email/`:

- `invitation_subject.txt`: one line, the subject. It reads *You are invited to PaceForge*.
- `invitation_message.txt`: the plain-text body. It has two variables: `signup_url`, the link, and
  `expires_at`, the expiry time in UTC. The body has `{% autoescape off %}`, so the `&` in the link
  is not written as `&amp;`. Keep the link on its own line.

The mail is plain text only. After you edit a template, restart the backend.

## Resend

**Resend** is on the row of every **pending** and **expired** invitation. Resending:

- creates a new link with a new token. **The old link stops working at once**, even if it was
  still valid,
- sets the expiry to now plus `INVITATION_TTL_DAYS`, so an expired invitation is pending again,
- keeps the same invitation, so the list gets no new row,
- sends one email, updates **Last sent** when the mail was delivered, and shows the new link once,
  with the same notices as on create.

**Used** and **revoked** invitations cannot be resent. The API answers `409`, and the page has no
**Resend** button for them.

## Expired invitations

An invitation is **expired** when its expiry time has passed and it was neither used nor revoked.
It stays in the list as a record. The page then:

- shows the status **Expired**, in its own style,
- shows a notice above the list with the number of expired invitations,
- offers **Resend** on the row.

## Revoke

The page offers **Revoke** only for **pending** invitations. Revoking makes the link stop working,
sets the status to **Revoked** and sends no mail. A revoked invitation cannot be resent; create a new
one instead. A used invitation cannot be revoked (`409`).

## Rate limit

Creating and resending share both limits:

- **20 per minute per administrator**, across all recipient addresses.
- **5 per hour per recipient address**, across all administrators. Address case does not matter.

The counters live in PostgreSQL and are shared by all workers. Clearing the process cache does
not reset them. The limits are set in `INVITATION_EMAIL_LIMITS` in `backend/config/settings.py`.
Reservations count even when mail delivery fails.

A request over either limit answers `429`. The `Retry-After` header gives the number of seconds
to wait. No invitation is created, no token is rotated and no mail is sent. Listing invitations
is not limited.

## Security and access

- Only administrators with two-factor authentication can use the API. Anyone else gets `403`. An
  administrator without two-factor authentication gets `403` with `"code": "mfa_required"`.
- The list shows every invitation of the instance, not only the ones you sent.
- The token is 256 bits of randomness. PaceForge stores only its SHA-256 hash. The plaintext token
  exists in the email and in the API response, once.
- PaceForge puts the token and address in the URL fragment (`#invitation=…&email=…`), so they
  stay in the browser and are not sent in HTTP requests or logged by proxies. The signup form
  still accepts older query links and removes the token and address from the visible URL after
  reading them. See [Signup links](#signup-links).
- Whoever has the link can register with that address until the invitation is used, revoked or
  expired. Send it only to the person it is for.
- The link uses `APP_ORIGIN`. It defaults to `https://<APP_DOMAIN>`, or `http://localhost:4200`
  in debug mode without a domain. The administrator's request host cannot change the link.
  Production requires a non-empty HTTPS origin. If you set only `DJANGO_ALLOWED_HOSTS`, add
  `APP_DOMAIN` or `APP_ORIGIN`.

## Admin API

All requests need a signed-in administrator with two-factor authentication. A `POST` also needs the
CSRF token, like every other `POST`.

| Request | What it does | Answers |
| --- | --- | --- |
| `GET /api/admin/invitations/` | Lists all invitations, newest first. | `200` |
| `POST /api/admin/invitations/` with `{"email": "ann@example.com"}` | Creates the invitation and sends one email. | `201` with `invite_url`, `delivery` and `email_sent`; `400` for a bad address; `429` over the limit |
| `POST /api/admin/invitations/<id>/resend/` | Issues a new link, expiry and email. | `200` with `invite_url`, `delivery` and `email_sent`; `404` unknown; `409` used or revoked; `429` |
| `POST /api/admin/invitations/<id>/revoke/` | Revokes a pending or expired invitation. | `200`; `404` unknown; `409` used |

Each invitation has these fields: `id`, `email`, `status` (`pending`, `used`, `revoked` or
`expired`), `created_at`, `expires_at` and `sent_at`. `sent_at` is `null` until a mail was
accepted by the mail system. Console output and failed attempts leave it unchanged, including on
resend. `invite_url`, `delivery` and `email_sent` come only with the create and resend answers.
`delivery` is `sent`, `console` or `failed`. `email_sent` is `true` only for `sent`. The list never
contains a link.

## Troubleshooting

- **The page says the email was only written to the server log.** Configure SMTP to send mail,
  or copy the link and send it yourself. This notice also appears after a console-only resend.
- **The page says the email could not be delivered.** Check the `SMTP_*` settings. The backend log
  names the invitation id and the type of the error. Then press **Resend**, or hand the link on.
- **Nothing arrives in development.** Check that Mailpit runs (`docker compose -f compose.dev.yaml
  up -d mailpit`) and open <http://localhost:8025>.
- **The mail arrives, but the link is refused.** A resend replaces the link. Use the newest mail, or
  resend again.

## For developers

- `backend/accounts/services/invitations.py`: creating, sending, resending and revoking, and the
  token hash.
- `backend/accounts/views.py`: `InvitationListCreateView`, `InvitationResendView` and
  `InvitationRevokeView`. Create validates the address before reserving; resend loads the stored
  address before reserving. Both map `InvitationLimitError` to `429` with `Retry-After`.
- `backend/accounts/services/invitation_limits.py`: atomic sender and recipient reservations in
  database counters. These reservations happen before creating an invitation or rotating a token.
- Tests: `backend/accounts/tests/test_invitations.py`, `test_invitation_limits.py` and
  `test_invitation_api.py`, and in the
  frontend `src/app/core/admin/invitations-api.spec.ts` and
  `src/app/features/admin/invitations-page.spec.ts`. The backend tests read sent mail from Django's
  test outbox, so no test contacts a real mail server.
