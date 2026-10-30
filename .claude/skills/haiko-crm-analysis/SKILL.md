---
name: haiko-crm-analysis
description: Understand a Dynamics 365 CRM well enough to build a Haiko app on it - asks which solutions, custom entities and core entities matter and who the contacts are, then reads the CRM's metadata (lookups to contact, business process flows, cloud flows, plugins, option sets, record counts) and writes workspace/<app>/crm-profile.md, ending in the journeys contacts go through. Use for "analyse my CRM", "start a new app", "what could we build", "what are our journeys", or whenever crm-profile.md is missing or stale.
---

# Haiko CRM analysis

You produce `workspace/<app>/crm-profile.md`. Every later skill builds on it, so
**every claim in it must come from the metadata or from the developer**, and say which.

Read-only: use only `scripts/crm.py`. Metadata and counts, never record contents.
On Windows run `python` (or `py`); on macOS, `python3`.

## 0. Before you start

- `python scripts/doctor.py` must say Ready. If not, use `haiko-setup`.
- Pick the app's folder name (short, lowercase, e.g. `student-app`). If `workspace/<app>/crm-profile.md` exists, read it and `decisions.md`, then ask what changed: **continue**, don't start again.

## 1. Ask (one or two questions at a time)

1. **Who uses the app?** In their words: students, tenants, patients, members. Use that word from now on.
2. **What should they be able to do?** Get two or three concrete things ("ask for wellbeing support", "see my placement and do my check-ins"). Map each to a pattern: *see my stuff*, *submit / request*, *track progress*, *communicate*, *receive information*.
3. **Which solutions hold the customisation?** Show the unmanaged and own-publisher solutions from `crm.py solutions`, and let them pick.
4. **Which entities are those journeys about?** Offer candidates from step 2 (custom entities in their solutions, plus `incident`, `appointment` and the like), with record counts. They confirm.

Don't ask what you can read. "Which field links a case to the student?" is answered by `contact-paths`.

## 2. Read the metadata

Save everything under `workspace/<app>/metadata/` with `--out`, so you can re-read it without asking the CRM again.

```
python scripts/crm.py solutions --out workspace/<app>/metadata/solutions.json
python scripts/crm.py entities --solution <uniquename> --out workspace/<app>/metadata/entities-<uniquename>.json
python scripts/crm.py counts <entity> <entity> ... --out workspace/<app>/metadata/counts.json
```

For **each core entity**:

```
python scripts/crm.py entity <entity>        --out workspace/<app>/metadata/<entity>.json
python scripts/crm.py contact-paths <entity> --out workspace/<app>/metadata/<entity>.paths.json
python scripts/crm.py processes --entity <entity> --out workspace/<app>/metadata/<entity>.processes.json
python scripts/crm.py plugin-steps --entity <entity> --out workspace/<app>/metadata/<entity>.plugins.json
```

Also run `processes` with no `--entity`. A cloud flow often has no primary entity (`none`), and its triggers show which entity it watches.

## 3. Work it out

For each core entity:

- **Who it belongs to.** From `contact-paths`, pick the **narrowest** path: `direct` beats `via`, and both beat `account`, which means every contact of that company. Note `polymorphic` lookups (`customerid` can also be an account). If there's more than one direct path (incident has `customerid`, `primarycontactid`, `responsiblecontactid`), **ask** which one means "this is the student's". Never pick silently.
- **What the contact would see.** The primary name, a few meaningful fields, and status reason labels (the `options` of `statuscode`).
- **What they could submit or change.** Fields valid for create/update, and which are required.
- **How it moves.** This is the heart of it:
  - **BPF stages** in order, with the fields each stage collects.
  - **Date stamps** (`ec_vettedon`, `ec_closedon`): a field that gets a date when something happens is the best proof a stage is done.
  - **Status reasons**: `statuscode` values that mark a step.
  - **Plugins and flows** that set fields on update of others (e.g. a plugin on update of `ec_approvedon` creates check-ins). They show cause and effect the BPF doesn't.

### Journeys

For each thing the contact tracks, write the journey as stages. Each stage gets:

- a **label in the contact's words** ("Advisor assigned", not "Stage 2")
- **done when**: the CRM fact that proves it happened, e.g. `hasValue(ec_vettedon)` or `statuscode == 450000003`
- **current when**: what's true while they're in it, e.g. `hasValue(ec_advisorid) AND isEmpty(ec_appointmenton)`
- **what the contact does**: nothing, wait, or act (and what)

**The rule: if a stage can't name the field or value that proves it, the stage is wrong.**
Mark it `UNPROVEN` and ask the developer what in the CRM changes when it happens.
Don't invent a field, and don't use `modifiedon` as proof.

Predicates use only: `hasValue(f)` `isEmpty(f)` `isTrue(f)` `isFalse(f)` `isPast(f)` `isFuture(f)` `contains(f, "text")`,
comparisons `== != > < >= <=`, and `AND OR NOT ( )`. Option values are numbers (`statuscode == 450000003`), never labels.

Also look for **ways out** (withdrawn, rejected, not approved). They are terminal stages with their own message.

Two checks before you're done:

- **Time-based stages.** Start and end dates (`ec_startdate`, `ec_enddate`) split a stage the BPF treats as one:
  approved but not started (`isFuture(ec_startdate)`), under way (`NOT isFuture(ec_startdate) AND isFuture(ec_enddate)`),
  finished but not wrapped up (`isPast(ec_enddate) AND isEmpty(<report stamp>)`). Students care about that difference.
- **Every status reason is accounted for.** Go through the `statuscode` labels of each journey's entity. Each one should be
  a stage, part of one, or a way out. A label with no stage ("Final report due") usually means a stage is missing,
  or a time-based split you haven't made.

## 4. Write `crm-profile.md`

Use this outline. Keep it short: a CRM developer should read it in five minutes.

```markdown
# <App> — CRM profile
CRM: <url> · Read: <date> · Solutions: <uniquenames>
Contacts are called: <word>

## What <word>s can do
- <thing> — <pattern> — <entity>

## Entities
### <entity> (<display name>, <count> records)
- Belongs to the <word> through: `<path>` (<kind>)  [chosen by <developer|metadata>]
- Shows: <fields>
- <Word> can submit: <fields> (required: <fields>)
- Status reasons: <value> <label>, ...
- Process: BPF "<name>": <stage> (<fields>) → ...
- Automation: <plugin/flow>: on <message> of <fields> → <effect>

## Journeys
### <journey name> (<entity>)
| # | Stage (<word>'s words) | Current when | Done when | <Word> does |
|---|---|---|---|---|
| 1 | ... | `...` | `...` | waits |
Ways out: <stage> when `<predicate>`.
UNPROVEN: <stage> — needs a field that records <what>.

## Open questions
- ...
```

Then add to `workspace/<app>/decisions.md` one line per thing the developer chose
(`<date> — chose customerid as the student link on incident: primarycontactid is the reporter`).

## 5. Check it with the developer

Walk through the journeys table and ask "is this how it works?" Fix what they
correct; update the profile and decisions. When they're happy, offer the
next step: "Shall we build the app?" (`haiko-app-builder`).
