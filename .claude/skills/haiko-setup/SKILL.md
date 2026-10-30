---
name: haiko-setup
description: Get a CRM developer's Windows or macOS machine ready for the Haiko Dev Kit, or work out why something doesn't run - installs Python, the Azure CLI, Git (and Node for plugins), signs in, sets up .env, and proves it with the doctor script. Use for "set up my machine", "install", "it doesn't work", "az login", "python not found", or before any other Haiko skill when doctor hasn't passed yet.
---

# Haiko setup

Goal: `doctor` prints **Ready.** Work through it one failure at a time. Don't
install anything the doctor doesn't ask for.

## 1. Run the doctor first

Find out what is already there before suggesting installs.

- **Windows** (PowerShell): `python scripts/doctor.py`. If `python` isn't found or opens the Microsoft Store, try `py scripts/doctor.py`.
- **macOS**: `python3 scripts/doctor.py`

If Python itself is missing, the command fails before the doctor runs; go to step 2.
Use `--json` when you want to read the results yourself, and `--offline` to check only the tools.

Every failure line has a `fix:`. Do that fix, then run the doctor again.

## 2. Install what's missing

Ask before installing, and install one thing at a time. Each command below is
what the developer runs. Windows uses **winget**, which is built into Windows 10 and 11.
macOS uses **Homebrew**: if `brew` isn't there, install it from https://brew.sh first.

| Tool | Version | Windows (PowerShell) | macOS (Terminal) | Why |
|---|---|---|---|---|
| Python | 3.12 (3.11 minimum) | `winget install Python.Python.3.12` | `brew install python@3.12` | every kit script |
| Azure CLI | current | `winget install Microsoft.AzureCLI` | `brew install azure-cli` | signs you in to your CRM |
| Git | current | `winget install Git.Git` | `xcode-select --install` | cloning this repo |
| Node.js | 20 LTS or later | `winget install OpenJS.NodeJS.LTS` | `brew install node@20` | **plugins only**: skip it until then |

Not needed: the Power Platform CLI (`pac`), the .NET SDK, Visual Studio, `pip`
packages and virtual environments. The kit's scripts use only Python's standard
library.

### Windows traps

- **Open a new terminal after every winget install.** PATH changes only reach new windows. "Not recognized" right after installing almost always means this.
- **`python` opens the Microsoft Store**, or prints nothing. That's a Store shortcut, not Python. Either use `py` instead of `python`, or turn the shortcut off: Settings → Apps → Advanced app settings → App execution aliases → switch off `python.exe` and `python3.exe`. Then open a new terminal.
- **winget isn't found.** Update "App Installer" from the Microsoft Store. On a locked-down work laptop, ask IT. The python.org installer works too: tick **Add python.exe to PATH**.
- **Corporate proxy**: if installs or `az login` time out, the developer's IT team will know the proxy settings. Don't guess them.

### macOS traps

- **Apple's own `python3` is too old** on some Macs (3.9). After `brew install python@3.12`, run `which python3`. It should be under `/opt/homebrew` (Apple silicon) or `/usr/local` (Intel). If not, open a new terminal, or use `python3.12` directly.
- `xcode-select --install` opens a window; the developer has to click Install.

## 3. Sign in to the CRM's tenant

```
az login --tenant <tenant> --allow-no-subscriptions
```

- Use the account they sign in to **Dynamics** with, not a personal Microsoft account.
- `<tenant>` is their organisation's domain (`contoso.onmicrosoft.com`) or tenant id. If they don't know it: in Dynamics, Settings (gear) → About shows it, or leave `--tenant` off and pick the account in the browser.
- `--allow-no-subscriptions` matters. Most CRM developers have no Azure subscription, and without the flag `az login` fails with "No subscriptions found".
- If the token step fails with **AADSTS53003** (or another AADSTS53xxx code), Conditional Access is blocking the Azure CLI. The developer can't fix that alone. Ask their admin to allow the Azure CLI for Dynamics 365, or stop here and say so.
- More than one tenant? Put `HAIKO_TENANT_ID=<tenant id>` in `.env` so the scripts always ask for the right one.

## 4. Fill in `.env`

Copy `.env.example` to `.env` (Windows: `copy .env.example .env`; macOS: `cp .env.example .env`), then set:

- `HAIKO_CRM_URL`: the address of their Dynamics, without any path, e.g. `https://contoso.crm11.dynamics.com`. From a browser address like `https://contoso.crm11.dynamics.com/main.aspx?appid=...`, keep only the part before `/main.aspx`.
- `HAIKO_STUDIO_ORG`: their Haiko Studio organisation id (Studio shows it in the address bar and Settings).
- `HAIKO_STUDIO_API_KEY`: Studio → Settings → API keys → name it after this machine → **Read and save drafts** → Create. It's shown once.

Never print the key, echo it back, or write it anywhere except `.env`.
The key can save drafts but can't publish a security manifest or start a build. That's by design.

## 5. Done

Run the doctor again. When it says **Ready.**, offer the next step:
"Shall we look at your CRM?" (the `haiko-crm-analysis` skill).
