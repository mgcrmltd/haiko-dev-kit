---
name: haiko-security
description: Build a Haiko app's security manifest - the rules the runtime API enforces about which records and fields a signed-in contact can read, create and change - with least privilege, a plain reason for every grant, and a question wherever the CRM is ambiguous. Saves it to Haiko Studio as a draft for a person to review and publish. Use for "security manifest", "who can see what", "least privilege", "lock it down", "why can't the app see X", or after building screens.
---

# Haiko security

The manifest decides what a contact's phone can reach in the CRM. Anything not
granted is refused. Your job: grant **exactly what the app uses, nothing more**,
and make every grant easy for a person to check.

You **cannot publish** the manifest, and that's on purpose. You save a draft. A person
signed in to Haiko Studio reviews it and publishes it. Until then the runtime API
keeps enforcing the last published version. Don't look for a way round this.

On Windows run `python` (or `py`); on macOS, `python3`.

## 1. What you need

- `workspace/<app>/app-definition.json`: pull it first (`python scripts/studio.py pull <appId> --into workspace/<app>`). The app's screens decide what's needed.
- `workspace/<app>/crm-profile.md`: who each record belongs to (the contact paths), decided with the developer.
- An existing `workspace/<app>/security-manifest.json`, if there is one: its action names and field mappings are kept.

## 2. Propose

```
python scripts/manifest.py --definition workspace/<app>/app-definition.json \
  --existing workspace/<app>/security-manifest.json \
  --link <entity>=<lookup to contact> ...  --shared <entity> ... \
  --out workspace/<app>/security-manifest.json --explain workspace/<app>/security-review.md
```

What it grants, and why that's least privilege:

| | Granted | Not granted |
|---|---|---|
| Whose records | `read: "own"` through the entity's link to the contact | other contacts' records |
| Which fields | `allowedFields`: every field a screen shows, a journey tests or a message mentions | every other column |
| Creating | `create: true` only where a form or workflow creates | everywhere else |
| Changing | `update: "own"` only where the app saves edits or runs a record action | everywhere else |
| Endpoints | only those the app calls | the rest, listed as "left out" in the review |
| Writing | `writableFields`: the fields a form creates with, or a journey lets the contact edit | any other field, even on the same record |

**Links.** For each entity, the link comes from `--link`, then the app's list screens (`customerField`), then the existing manifest.
Use the narrowest path from `crm-profile.md`: a **direct** lookup to contact. If the profile marked a choice as the developer's, use theirs.
If an entity has more than one candidate and the profile doesn't say, **ask**: "A case has customerid, primarycontactid and responsiblecontactid. Which one means it's the student's?"

**Shared content** (news, FAQs, offices) has no owner. Only pass `--shared <entity>` after the developer has said every signed-in contact may see every record.

**Problems** ("needs an answer") are things the script refused to guess: an entity with no link, an edit with nowhere to save.
Ask the developer, then run it again with `--link` or `--shared`. Never resolve one by widening a grant.

Things to raise even when the script is happy:
- A link through **account** (every contact at the company sees the record). Say so in plain words and ask if that's intended.
- A **polymorphic** link (`customerid` can be an account). Records whose customer is an account won't show for any contact.
- **`read: "all"`** on anything that isn't obviously public.
- An endpoint with **no `writableFields`**: it can write any field. The script always sets them, so if one is missing someone removed it.

## 3. Check

```
python scripts/crmcheck.py --definition workspace/<app>/app-definition.json --manifest workspace/<app>/security-manifest.json
python scripts/studio.py validate --app <appId> --manifest workspace/<app>/security-manifest.json
```

`crmcheck` proves every field and entity exists and every link really is a lookup to contact.
`validate` checks the manifest's shape and that it covers every entity and endpoint the app uses.
Fix everything both report.

## 4. Explain, then save as a draft

Show the developer `workspace/<app>/security-review.md` in plain words. For each entity: whose records, which fields, and create/update yes or no.
Walk through it; change what they want changed (and re-run steps 2 and 3).

When they agree:

```
python scripts/studio.py save <appId> --manifest workspace/<app>/security-manifest.json
```

It reports `manifestState: unpublished`. Tell the developer exactly this:

> The manifest is saved in Haiko Studio as a draft. Open the app in Studio → **Security**: a banner says it isn't published.
> Review it there, then press **Publish security manifest**. Until you do, the runtime API keeps enforcing the previous one.

Add the decisions to `workspace/<app>/decisions.md` (links chosen, anything made shared, anything left out on purpose).
