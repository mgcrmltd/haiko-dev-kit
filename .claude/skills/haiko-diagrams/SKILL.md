---
name: haiko-diagrams
description: Draw a Haiko app as one draw.io file with a tab per diagram - an overview, screens and navigation, endpoints and architecture (down to the CRM plugins and cloud flows that react to what the app writes), a journey diagram per journey and a wizard diagram per multi-step form. Use for "draw my app", "diagram", "draw.io", "show me the journeys", "architecture diagram", "how does it all fit together", or to explain an app to someone.
---

# Haiko diagrams

One command turns an app into a `.drawio` file people can open, read and edit.
It reads files only; nothing is changed in Studio or the CRM.

On Windows run `python` (or `py`); on macOS, `python3`.

## 1. Get the app

- From Studio (the usual way): `python scripts/studio.py pull <appId> --into workspace/<app>`
- Or from a snapshot the developer exported from Studio: use `--snapshot <file>` below instead of `--app`.

## 2. Offer the CRM side (architecture tab)

The architecture tab can follow each endpoint into Dynamics, to the plugins and cloud flows that fire
when the app creates or changes a record. That needs the CRM's metadata on this machine. If
`workspace/<app>/metadata/` has `*.plugins.json` and `processes.json` already (the CRM analysis saves them), use them.
Otherwise offer to read them, read-only (`haiko-setup` must have passed):

```
python scripts/crm.py plugin-steps --out workspace/<app>/metadata/plugins.json
python scripts/crm.py processes --out workspace/<app>/metadata/processes.json
```

Without them the file is still complete; the architecture tab just stops at the tables and Custom APIs.

## 3. Draw

```
python scripts/diagram.py --app workspace/<app> --out workspace/<app>/<app>.drawio
python scripts/diagram.py --snapshot <snapshot.json> [--metadata workspace/<app>/metadata] --out <app>.drawio
```

It prints the tabs it drew. The same app always draws the same file, so redraw freely after changes.

## 4. Tell the developer how to open it

- **draw.io desktop** (free, Windows and macOS: https://www.drawio.com), or **app.diagrams.net** in a browser (File, then Open from, then Device).
- **VS Code**: the "Draw.io Integration" extension opens `.drawio` files in the editor.

Then say in a sentence or two what each tab shows, and point out anything the diagrams flag in red or amber:

- an endpoint **not in the security manifest** (the API will refuse it), or one with **no writableFields** (it can write any field): suggest `haiko-security`
- a table with **no security policy**: suggest `haiko-security`
- in a journey, a field marked **(editable)** that the contact shouldn't change: suggest `haiko-app-builder`

The diagrams are generated: edits made in draw.io are lost when it's redrawn. To change the app, change it in Studio or with
`haiko-app-builder`, then redraw.
