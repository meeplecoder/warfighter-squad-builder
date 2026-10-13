# Contributing

Thanks for helping! This is a small fan project; every kind of contribution is welcome — bug reports, ideas, rule
fixes, translations, documentation and code.

## Content policy (please read)

This project is **unofficial**. *Warfighter* and everything that makes up its cards belongs to DVG (see
[NOTICE.md](NOTICE.md)). Therefore:

- **Never** add DVG's card text, rulebook text, card scans or artwork to the repository, an issue or a pull request —
  not even "just a few cards". Use the fictional demo set in [`examples/`](examples/cards.sample.csv) for tests,
  screenshots and bug reports.
- Describe rules problems in your own words and point at the page of the rulebook.
- Third-party fan content (campaigns, squad lists) may only be added with its author's permission and credit.

## Ways to contribute

- **Report a bug or propose a feature** — open an issue (templates are provided). For a rules question, say which card
  or rule is involved *without copying its text*.
- **Translate** — the UI strings live in `static/i18n/<lang>.json` and server messages in `app/translations/`. To add a
  language, add its code to `SUPPORTED_LANGS` in `app/i18n.py`, create the two files by copying `en`, and check
  coverage with `python scripts/i18n_check.py`. Card texts are translated through the import/export scripts
  (`scripts/import_translations.py`).
- **Improve the squad metrics / generator** — skills the metrics understand are listed in one table,
  `app/skill_effects.py`; adding a skill there makes both the metrics and the generator aware of it.
- **Docs and tests** — always welcome.

For anything bigger than a small fix, please open an issue first so we can agree on the approach.

## Development setup

Follow [INSTALL.md](INSTALL.md) (sections 1–5), then:

```bash
pip install -r requirements-dev.txt
pytest                      # runs against a temporary database built from the demo cards
python scripts/i18n_check.py
```

There is **no build step**: the frontend is plain JavaScript in `static/`. Python code is formatted in the style of the
surrounding file (PEP 8, 4 spaces; match the existing comment density and naming).

## Making a change

1. Fork the repository and create a branch from `main`.
2. Keep the change focused; write or update tests when behaviour changes (`tests/`).
3. If you add or change UI text, add the key to **both** `static/i18n/en.json` and `static/i18n/es.json`
   (machine translations are fine as a first pass — mark them in the PR) and run `python scripts/i18n_check.py`.
4. Database changes: models live in `app/models.py`; new tables are created automatically, and new columns on existing
   tables need a small safe `ALTER TABLE` in `create_app` (see how the existing ones are done). Never require
   a manual migration step for users.
5. Run `pytest` and make sure it passes. JavaScript can be syntax-checked with `node --check static/*.js`.
6. Open a pull request using the template. Describe *what* changed and *why*, and add screenshots for UI changes
   (taken with the demo data).

### Commit messages

Short imperative summary with a prefix: `FEAT:`, `FIX:`, `UI:`, `PERF:`, `DOCS:`, `TEST:`, `REFACTOR:`; details in the
body. Example: `FIX: nation check compares base nations (US Airborne cards in a US squad)`.

### Privacy tip

Commits carry the author name and email from your git configuration. If you do not want your address public, use
GitHub's no-reply address (Settings → Emails → *Keep my email addresses private*) and set
`git config user.email "<id>+<username>@users.noreply.github.com"` in your clone.

## Licensing of contributions

By submitting a contribution you agree that it is licensed under the project's [MIT License](LICENSE), and that you
have the right to submit it (in particular, that it contains no DVG-owned text or artwork and no code copied from
an incompatibly licensed project).

## Code of conduct and security

Be kind: see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Report vulnerabilities privately as described in
[SECURITY.md](SECURITY.md) — not in public issues.
