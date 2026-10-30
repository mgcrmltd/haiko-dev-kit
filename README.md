# Haiko Dev Kit

Build a Haiko app for your Dynamics 365 contacts with an AI coding agent.

Clone this repo, open it in Claude Code (or another agent that reads `AGENTS.md`), and say what you want:

> "Set up my machine." · "Analyse my CRM." · "Build my app." · "Write the security manifest." · "I need a plugin that…" · "Draw my app."

The agent uses the skills in this repo to look at your CRM, ask you the right questions, and build your app in Haiko Studio. You stay in charge: you answer the questions, review what it proposes, and you publish.

## What it does

| Skill | What it does |
|---|---|
| **Setup** | Installs and checks what the kit needs, on Windows or macOS. |
| **CRM analysis** | Asks which solutions, entities and processes matter, reads your CRM's metadata, and works out the journeys your contacts go through. |
| **App builder** | Starts a new app in Haiko Studio, or continues one, from that analysis. Checks it and saves it as a draft you can see in Studio's Preview. |
| **Security** | Works out the least each screen needs to see, and writes the security manifest. You review it and publish it in Studio. |
| **Plugins** | Designs, builds and tests a plugin when the app needs something configuration can't do. |
| **Diagrams** | Draws the app as one draw.io file: screens and navigation, architecture down to the CRM's plugins and flows, each journey and each multi-step form. |

## Your data

The kit is built so that you can say yes to it in a security review.

- **Metadata only.** The kit reads your CRM's *structure*: entities, fields, relationships, option sets, business process flows, cloud flow definitions and solutions. It also counts records. It never reads the contents of a record, so no contact's data reaches the agent or Haiko Studio.
- **Read-only.** Nothing in this kit writes to your CRM. You can check: every CRM call is in [`scripts/crm.py`](scripts/crm.py), and its tests fail if a write is added.
- **Your identity, on your machine.** The kit uses your own sign-in (`az login`). Haiko Studio never holds a credential to your CRM and never connects to it. Traffic goes one way: from your machine to Studio, when you save.
- **A person publishes.** The kit's Studio key can save drafts. It cannot publish a security manifest; only a person signed in to Studio can.
- **Your choice of AI.** The CRM metadata the kit reads goes to whichever AI agent you run it with. Choosing that agent, and whether it is approved in your organisation, is your decision.

## Quick start

You need **Python 3.11 or later** (3.12 recommended), the **Azure CLI** and **Git**. For plugins, also **Node.js 20**. The setup skill installs and checks all of these. Ask your agent to "set up my machine", or follow [`.claude/skills/haiko-setup/SKILL.md`](.claude/skills/haiko-setup/SKILL.md) yourself.

```bash
git clone https://github.com/mgcrmltd/pwr-ntv-dev-kit.git
cd pwr-ntv-dev-kit
python scripts/doctor.py --org https://yourorg.crm11.dynamics.com    # on macOS: python3
```

Then copy `.env.example` to `.env` and fill it in:

- your CRM's URL
- your Haiko Studio organisation id
- a Studio API key (Studio → Settings → API keys)

`.env` is never committed.

## How it is laid out

```
AGENTS.md            the agent's entry point: which skill to use when
.claude/skills/      the skills (Agent Skills format: one folder per skill, SKILL.md inside)
scripts/             Python, standard library only:
  doctor.py            checks the machine, the CRM sign-in and the Studio key
  crm.py               read-only CRM metadata (entities, contact paths, processes, counts)
  crmcheck.py          checks every CRM name an app uses against the CRM
  manifest.py          proposes a least-privilege security manifest, with reasons
  studio.py            Haiko Studio: pull, validate, create, save drafts, preview
  diagram.py           draws an app as a draw.io file, a tab per diagram
schemas/             JSON Schemas for the app definition and security manifest
examples/            a complete app and manifest to learn from
plugin-starter/      the starting point for a plugin (needs Node 20)
workspace/<app>/     what the skills learn and decide, per app (not committed)
```

> Plugins: `npm install` in a plugin downloads Haiko's plugin packages from Haiko Studio using your Studio API key,
> read from the `HAIKO_STUDIO_API_KEY` environment variable. No other token is needed.

The skills hand work to each other through files in `workspace/<app>/`: `crm-profile.md`, `decisions.md` and the drafts. So "carry on building my app" works in a new session, or for a colleague.

## Licence

MIT. See [LICENSE](LICENSE).
