---
name: haiko-app-builder
description: Start a new Haiko app in Haiko Studio, or continue an existing one, from the CRM profile - asks what contacts need to do, proposes screens, journeys and navigation, writes the app definition, checks every CRM name and Studio's own rules, and saves it as a draft that Studio's Preview builds. Use for "build my app", "add a screen", "change the journey", "continue my app", "show me it in Studio".
---

# Haiko app builder

You write `workspace/<app>/app-definition.json` and save it to Haiko Studio.
Studio rebuilds its **Preview** after every save, so the developer sees the app
straight away.

Rules:
- Build from `workspace/<app>/crm-profile.md`. If it's missing, run `haiko-crm-analysis` first.
- Every CRM name comes from the profile or the metadata (`workspace/<app>/metadata/`, or `scripts/crm.py`). Never guess one.
- Before every save, both checks pass: `scripts/crmcheck.py` (CRM names) and `scripts/studio.py validate` (Studio's rules). `studio.py save` refuses to send otherwise.
- You can't publish anything. The security manifest is `haiko-security`'s job, and a person publishes it.

On Windows run `python` (or `py`); on macOS, `python3`.

## 1. New or continuing?

```
python scripts/studio.py apps
```

- **Continuing:** `python scripts/studio.py pull <appId> --into workspace/<app>`, then read the definition and `decisions.md`. Ask what to change.
- **New:** confirm the app's name and its id (a short slug, e.g. `student-app`). You'll create it at the first save.

## 2. Agree what to build

From the profile's "What <contacts> can do", propose the app as a list the developer can say yes to, like this:

> **Home** with cards for: Ask for support · My requests · My placement
> **Ask for support**: a form on `incident` (category, urgency, what's going on, consent)
> **My requests**: a list of the student's cases → each opens with the wellbeing journey
> **Propose a placement**: three steps (employer, role, dates) creating an `ec_placement`

Ask about anything the profile leaves open. Write the agreed shape in `decisions.md`.

## 3. Write the definition

The contract is `schemas/app-definition.schema.json`, and every property and enum is there.
`examples/empirical-college/app-definition.json` is a complete working app: copy its patterns.

Recipes, one per pattern:

| The contact wants to… | Build | Key properties |
|---|---|---|
| **see my stuff** | `list` screen → `record` screen | list: `entity`, `customerField` (the profile's contact link), `titleField`, `subtitleField`, `dateField`, `detailScreenId`, `allowCreate`. record: `sections`, `fields` with `showOnView` |
| **submit / request** | `form` screen + an endpoint | form: `fields` with `showOnCreate`, `required`; `createEndpointIds: [<endpoint>]`. Endpoint: `{ id, name, type: "d365_direct", uri: "<entity>", submitMessage }` |
| **several steps** | `workflow` with `form` steps | `steps[]` of `{ id, label, order, type: "form", formScreenId }`, `submitEndpointId`, `completionMessage` |
| **track progress** | a `journey` on the record screen | copy the profile's journey table: one stage per row (below) |
| **receive information** | `list` of shared content, `rss-feed` or `webview` screen | shared entities have no contact link; the manifest gives them `read: "all"` |

**Fields.** Map from the CRM type in the metadata:

| CRM type | `type` | Notes |
|---|---|---|
| StringType | `text` (`email`, `phone`, `url` when it is one) | `maxLength`: the field's `maxLength` in `crm.py entity` (the column's limit), or less if the developer wants |
| MemoType | `textarea` | `maxLength` the same way |
| PicklistType | `optionset` | `options`: `{ value: "<number as string>", label, order }` taken from the metadata, never made up |
| DateTimeType | `date` or `datetime` | |
| BooleanType | `boolean` | |
| Integer / Decimal / Money | `number` / `decimal` / `currency` | |
| LookupType | `lookup` | needs `lookupConfig` (a list screen or a `d365_action` endpoint for its options); a lookup the contact can't choose is best left out of forms |
| FileType | `file` | check with the developer that file upload is enabled for their app before promising it |

Every field also needs `label` (in the contact's words), `crmField: true`, `required`, `showOnCreate`, `showOnView`, `order`, and a `section` that exists in the screen's `sections`.

**Journeys.** Copy each row of the profile's journey into a stage:

```json
{ "id": "choose", "label": "Choose an appointment", "order": 3,
  "activeWhen": "statuscode == 450000003", "completeWhen": "hasValue(ec_appointmenton)",
  "message": "Pick a time that suits you, then save.", "contactAction": "action_required",
  "showFields": ["ec_appointmenton"], "dateField": "ec_appointmenton" }
```

- `message`: what the contact reads while in this stage: plain, kind, and in their words. `{field.name}` puts a lookup's name in.
- `contactAction`: `none`, `waiting` or `action_required`.
- **`showFields` are editable by the contact** while the stage is current, unless they're also in `readOnlyFields`.
  Anything the contact should only see (an appointment time, a decision) goes in both. Only leave a field editable
  when the contact is meant to fill it in at that stage (a final report, a check-in response): `haiko-security` grants
  write access to exactly those.
- A way out (withdrawn, not approved) gets `"pathRole": "terminal"`, `"order": 0` and `"completeWhen": "isEmpty(createdon)"` (never complete).
- The journey also needs `defaultMessage` and `defaultContactAction`.

**Navigation.** Each item is `{ id, label, icon, order, target }`. The first is `{ id: "home", label: "Home", target: { type: "dashboard" } }`.
Then add one item per thing the contact does, with `target` `{ type: "form" | "list", screenId }` or `{ type: "workflow", workflowId }`.

**Theme and auth.** On a new app, ask for brand colours (or keep the example's) and take `auth` from the developer: their Haiko
API URL and app registration. If they don't have them yet, use the example's placeholders and say saving will report them until they're filled in.

## 4. Check, save, look

```
python scripts/crmcheck.py --definition workspace/<app>/app-definition.json
python scripts/studio.py validate --definition workspace/<app>/app-definition.json [--app <appId>]
python scripts/studio.py create --definition workspace/<app>/app-definition.json          # first time
python scripts/studio.py save <appId> --definition workspace/<app>/app-definition.json    # after that
python scripts/studio.py preview <appId> --wait
```

Fix every problem the checks report. Each one names its path. Don't save around them.

When the preview is `ready`, tell the developer to open the app in Haiko Studio: **Preview** shows it with sample data.
If it's `failed`, read `lastFailure` and fix what it says.

**Data won't show until there's a security manifest.** The runtime API refuses any entity without a policy, and `validate` warns about each one.
Once the screens are agreed, offer `haiko-security`.

## 5. Changing an existing app

Pull first, every time. Someone may have changed it in Studio since. Change only what was asked, keep everything
else as it was, and save the whole definition. Say what you changed in one line, and add it to `decisions.md`.
