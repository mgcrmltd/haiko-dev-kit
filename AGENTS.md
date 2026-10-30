# Haiko Dev Kit: instructions for the agent

You are helping a **CRM developer** build a Haiko app: a mobile app for the
**contacts** in their Dynamics 365 (customers, tenants, students, patients), not for
the staff who use Dynamics. Contacts see their own records, submit things, track
progress, hear from the organisation and talk to it. Everything is scoped to the
signed-in contact.

## Which skill to use

Skills live in `.claude/skills/<name>/SKILL.md`. Read the whole SKILL.md before acting on it.

| The developer wants to… | Skill |
|---|---|
| install or check tools, sign in, "it doesn't work" | `haiko-setup` |
| understand their CRM, start from scratch, "what could we build?" | `haiko-crm-analysis` |
| create or change an app, screens, journeys, navigation | `haiko-app-builder` |
| the security manifest, "who can see what", least privilege | `haiko-security` |
| something configuration can't do: a custom screen, widget, field or wizard step | `haiko-plugins` |

Order for a new app: setup → CRM analysis → app builder → security. Plugins at
any point after the app exists. If `workspace/<app>/crm-profile.md` is missing,
run the CRM analysis before building anything.

## Rules that are never relaxed

1. **The CRM is read-only.** Only use `scripts/crm.py` to talk to Dataverse. Never
   write a request that creates, updates or deletes anything in the CRM, even
   if asked. Say that the kit can't, and suggest doing it in the maker portal.
2. **Metadata, not data.** Never fetch record contents. Counts are fine. If the
   developer pastes record data into the chat, don't copy it into workspace files.
3. **You don't publish security manifests.** Save them as drafts; tell the
   developer to review and publish in Haiko Studio. The kit's key can't publish
   anyway; don't look for a way around that.
4. **Validate before every save** to Studio (`scripts/studio.py validate`), and
   check every CRM name you use against the metadata. Never invent an entity,
   field, option value or relationship. Where you don't know, ask.
5. **Write down decisions.** Each time the developer chooses something, add a
   line to `workspace/<app>/decisions.md` with the choice and the reason.
6. **Secrets stay in `.env`.** Never print the API key or a token, and never
   write one to any other file.

## Talking to the developer

They know their CRM well and Haiko less well. Use their organisation's words
(say "students", not "contacts", if that's what they are). Ask one or two
questions at a time, offering choices where you can. When you propose
something, say which CRM fact it rests on.

## Scripts

All Python, standard library only. Run them with `python` on Windows (or `py`) and `python3` on macOS.

- `scripts/doctor.py`: checks the machine, the CRM sign-in and the Studio key
- `scripts/crm.py`: read-only CRM metadata (`python scripts/crm.py --help`)
- `scripts/studio.py`: Haiko Studio API: get, validate, save draft (`--help`)
