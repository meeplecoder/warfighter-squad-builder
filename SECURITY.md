# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private reporting instead:
**Security tab → "Report a vulnerability"** on the repository page. Include what you found, how to reproduce it, and
the version or commit you tested. You will get an acknowledgement as soon as the maintainer can, and credit in the fix
if you want it.

## Scope

In scope: the application code in this repository — authentication (registration, email verification, login, password
reset, session handling), authorization (who can edit which squad/campaign/translation), injection or XSS in the API
and frontend, rate-limit bypasses, and unsafe defaults.

Out of scope: problems that need a misconfigured server (running `DEBUG=true` in production, ignoring the checklist in
[INSTALL.md](INSTALL.md) §9), denial of service by raw traffic volume, and vulnerabilities in third-party services.

## Supported versions

Only the latest commit on `main` is supported; the project does not publish versioned releases yet.

## Notes for people who host an instance

- Run with `DEBUG=false`; the app then refuses to start without a strong `SECRET_KEY` and an `APP_BASE_URL`.
- Serve over HTTPS and keep `COOKIE_SECURE` on (the default outside development).
- Use a real mail backend (`smtp` or `resend`) so verification and reset emails are delivered.
- Run a single worker process (rate-limit counters are in memory) and back up `data/warfighter.db`.
