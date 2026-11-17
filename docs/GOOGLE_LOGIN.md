# Sign in with Google

AutoManga can let remote browsers sign in with a Google account (OpenID
Connect) instead of, or as well as, the password. Requests from the server
itself (loopback: MCP tools, `agent_cli`, the Comics converter, a browser on
that Mac) never need to sign in.

Google can only send the browser back to an **https** address that you
register in advance, so Google sign-in works on the public name only, here
`https://manga.madebypless.dk`. The LAN address (`http://192.168.1.177:5180`)
shows the password form, if it is on, and a link to the public name.

You need a Google account and about 10 minutes.

## 1. Google Cloud Console

1. Open <https://console.cloud.google.com/>, then use the project picker at
   the top to choose **New project**. Name it, for example `AutoManga`, and
   select it.
2. Open **Google Auth Platform** (APIs & Services → OAuth consent screen).
   Click **Get started**:
   - **App information**: app name `AutoManga`, user support email = your
     address.
   - **Audience**: **External**.
   - **Contact information**: your address.
   - Accept the policy and click **Create**.
3. **Audience** → **Test users** → **Add users**: add your own Google address
   (and anyone else who should sign in). The app can stay in **Testing**
   mode. The basic scopes need no verification, and only test users can sign
   in, which suits a private server. Testing mode limits refresh tokens to 7
   days, but AutoManga does not use refresh tokens, so that limit does not
   apply here.
4. **Data access** → **Add or remove scopes**: tick `openid`,
   `.../auth/userinfo.email` and `.../auth/userinfo.profile`, then
   **Update** → **Save**. These are the non-sensitive defaults.
5. **Clients** → **Create client**:
   - Application type: **Web application**, name e.g. `AutoManga web`.
   - **Authorized redirect URIs** → **Add URI**:
     `https://manga.madebypless.dk/api/auth/google/callback`
     (exactly this: https, no trailing slash).
   - **Authorized JavaScript origins**: leave empty (not needed).
   - **Create**. Copy the **Client ID** and **Client secret** from the dialog.
     Download the JSON if you like, but don't put it in the repository.

A new client can take a few minutes to start working. Until then Google
shows an error such as `invalid_client` or `redirect_uri_mismatch`.

## 2. On the server

```sh
cd ~/TT_AutoManga
.venv/bin/python -m backend.core.auth set-google          # paste the client id, then the secret (hidden)
.venv/bin/python -m backend.core.auth allow-email you@gmail.com
.venv/bin/python -m backend.core.auth set-public-url https://manga.madebypless.dk
.venv/bin/python -m backend.core.auth status              # check it (prints no secrets)
launchctl kickstart -k gui/$(id -u)/dk.madebypless.automanga   # restart the service
```

- `set-google` stores the client id and secret in `data/auth.json` (chmod
  600, next to the password hash), never in `data/settings.json`. No API
  returns them. To script it, run
  `printf '%s\n%s\n' "$ID" "$SECRET" | … set-google --stdin`. To remove the
  client, run `clear-google`.
- `allow-email` / `deny-email` edit `auth.googleAllowedEmails` in
  `data/settings.json`. Addresses are exact and lowercased. Removing an
  address signs that account out at once. Once Google sign-in works, you can
  also edit the list in **Settings → Access**.
- `set-public-url` sets `auth.publicUrl`, which must be https and have no
  path, and adds its host to `auth.allowedHosts`.
- The CLI writes the settings file on disk, and the running server keeps its
  settings in memory, so **restart the service** after these commands.

Caddy needs no change. It already forwards `X-Forwarded-For`,
`X-Forwarded-Proto` and the original Host from `192.168.1.11`
(`auth.trustedProxy`).

## 3. Try it

Open `https://manga.madebypless.dk` in a private window. Click **Sign in with
Google**, pick your account, and you land back in the app. In **Settings →
Access** you should see "Signed in as you@gmail.com".

## 4. Optional: turn the password off

In **Settings → Access**, switch off **Allow password sign-in**. After that,
remote browsers can only use Google. The server refuses the switch (409)
unless Google is set up and at least one address is allowed. You can always
get back in from the server itself, because loopback is exempt. Open
`http://127.0.0.1:5180` there and switch it back on, or edit
`auth.passwordLogin` in `data/settings.json` and restart. Sessions that are
already signed in stay valid. Run `logout-all` to end them.

## Errors after a sign-in attempt

The app shows a message, and the URL briefly carries `?login_error=`:

| code            | meaning |
|-----------------|---------|
| `denied`        | You cancelled on Google's page. |
| `not_allowed`   | The Google account is not in `googleAllowedEmails`. |
| `invalid`       | The sign-in expired or is invalid (state or nonce mismatch, token rejected, Google unreachable). Try again. |
| `misconfigured` | No client or no publicUrl, or Google rejected the client (`invalid_client`: wrong secret). |
| `rate`          | Too many failed attempts from this address (the same limiter as the password). |

The server log has the reason, and it never logs tokens. `redirect_uri_mismatch` on Google's own page
means the URI in step 1.5 differs from `<publicUrl>/api/auth/google/callback`.

## How it works

The browser goes to `GET /api/auth/google/start?next=/path`. The server
redirects to Google with the authorization code flow, PKCE (S256), a random
state, a nonce and `prompt=select_account`. These values and `next` are kept
in a signed, HttpOnly, 10-minute `am_oauth` cookie, not in server memory, so a
restart doesn't break a sign-in that is in progress. Google then calls
`/api/auth/google/callback`. The server checks the state, exchanges the code
at `https://oauth2.googleapis.com/token`, and validates the ID token's claims:
issuer, audience, expiry, nonce, `email_verified` and the allowlist. The ID
token comes straight from Google over TLS, so OIDC Core §3.1.3.7 lets the
server skip the signature check. If everything checks out, the server sets the
usual `am_session` cookie, which now includes the email, and redirects to
`next`. `next` is only accepted as a relative path on this site.
