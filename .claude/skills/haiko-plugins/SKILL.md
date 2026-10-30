---
name: haiko-plugins
description: Design, build, test and pack a Haiko plugin - a React Native component compiled into a Haiko app as a screen, dashboard widget, form field or wizard step - when configuration alone can't do what the contacts need. Asks what the contact should see and do, explains what's possible and the common patterns, builds from the kit's plugin starter, tests against mock data, validates and packs it, and walks the developer through upload and placement in Haiko Studio. Use for "plugin", "custom screen", "widget", "I need something the app can't do", "a map", "a custom field".
---

# Haiko plugins

A plugin is a small React Native component that Haiko compiles into the app in
one **slot**. It reads and writes the contact's own CRM data through the
Haiko SDK, which enforces the same security as the rest of the app.
Everything about the SDK, the manifest, native modules and the validator is in
[reference.md](reference.md). Read the parts you need before writing code.

## 1. Is a plugin the answer?

Check configuration first: a plugin is code someone has to maintain.
- A list, a form, a record page, a journey, a multi-step form: **configuration** (`haiko-app-builder`).
- Something configuration has no screen type for: a map, a "next appointment" card on the home page, a custom input (a slot picker, a signature-style confirmation), a step that calls a CRM action and shows the answer: **plugin**.

## 2. Ask

1. **What should the contact see, and what can they do?** Get a concrete example ("on the home page, my next appointment: when, where, with whom").
2. **Where?** Pick the slot:

| Slot | Appears | Gets | Good for |
|---|---|---|---|
| `widget` | a card on the home dashboard, below the configured cards | `config`, `openScreen(screenId)` | "my next…", a summary, a shortcut |
| `screen` | a whole page; navigation, dashboard cards and journey buttons can open it | `config` | a map, a richer view, a mini-tool |
| `field` | one input inside a form or journey stage (the form draws the label and errors) | `value`, `onChange`, `required`, `error`, `form` … | a picker the built-in types can't do |
| `step` | a whole step of a multi-step form | `values`, `setValues`, `registerValidate` | a check or calculation mid-wizard |

3. **What data?** Which entities and columns it reads (from `crm-profile.md`), anything it creates or updates (exactly which columns), any CRM Custom API it calls.
4. **Anything outside the CRM?** A service needing a key goes through a **proxy** (the key stays on the customer's server). A keyless public one can be an `externalHost`. Device features only from the native module allowlist (location, maps, camera, image picker, haptics, webview).

### What isn't possible, so say so plainly

- Other contacts' data. Every read is the signed-in contact's own rows, enforced by the server.
- Joins or OR in queries. One entity per `useQuery`, conditions ANDed. Use two queries, or a Custom API.
- Native modules not on the allowlist, background tasks, or anything installed at runtime.
- Calling a service with a secret from the phone. That's what proxies are for.
- Uploading the plugin yourself. A person in Studio does that (MGCRM staff, for now).

## 3. Build

On Windows run `python`/`npm` the same way as on macOS; Node 20+ is needed (`haiko-setup` checks it).

```
cp -r plugin-starter workspace/<app>/plugins/<plugin-folder>        # Windows: xcopy /E /I plugin-starter workspace\<app>\plugins\<plugin-folder>
# copy it without node_modules or dist if they exist there, and always npm install in the copy
cd workspace/<app>/plugins/<plugin-folder>
npm install
```

> Haiko's plugin packages come from Haiko Studio with the developer's Studio API key: `npm install` reads it from the
> **environment variable** `HAIKO_STUDIO_API_KEY` (not from `.env`). Set it first. Windows: `setx HAIKO_STUDIO_API_KEY "<key>"`, then
> open a new terminal. macOS: add `export HAIKO_STUDIO_API_KEY="<key>"` to `~/.zshrc` and open a new terminal.
> A 401 on `@mgcrm-haiko-builds/...` means it isn't set or the key was revoked.

Then, in this order:

1. **Manifest** (`haiko-plugin.json`): a lowercase reverse-DNS `id` the developer owns (`com.<org>.<name>`), `version` `1.0.0`, `displayName`, `description`, `author`, **only the slots you need**, and `data` / `proxies` / `externalHosts` / `nativeModules` declaring **every** column, write, action and host the code uses. Undeclared ones are refused at runtime.
2. **Code** (`src/index.tsx`): one export per slot, with the name in `export`. Use the hooks (`useQuery`, `useRecord`, `useSubmit`, `useAction`, `useProxy`, `useTheme`, `useNavigation`). Use theme colours, not your own. Show `error.userMessage` when set; otherwise say something general. Never show `error.message`. Settings may be missing, so always have a fallback.
3. **Remove the starter's other samples** from `src/index.tsx`, `preview/App.tsx` and `__tests__/plugin.test.tsx` (typecheck fails until you do).
4. **Tests** (`__tests__/`): render each slot in `MockHaikoHost` with `createMockHost({ tables, writes, actions, proxies, config })`. Cover: data shown, the empty state, a failing read (`PluginError` with a `userMessage`), and any write or action.
5. **Accessibility** (WCAG 2.2 AA, gated by the validator): every touchable has `accessibilityLabel`, `accessibilityRole` and `accessibilityHint`; headings `accessibilityRole="header"`; errors `role="alert"` + `accessibilityLiveRegion="assertive"`; minimum height 48; never `allowFontScaling={false}`. The full checklist is in reference.md.

```
npm test
npm run typecheck
npm run validate        # the same checks Studio runs on upload; codes HP001–HP063 in reference.md
npm run pack            # dist/<id>-<version>.zip
```

All four must pass. Fix what they report. Never work around a validator code.

### Common patterns

- **"My next …" widget**: `useQuery` on the entity with `where: [{ attribute: "<date>", operator: "ge", value: now }]` (`now` worked out once with `useState`), `orderBy` that date, `top: 1`. Show an empty state. Add a `screenId` setting and a button that calls `openScreen(config.screenId)`.
- **Look something up outside the CRM** (postcode, opening hours): a `proxy` with `useProxy(id).request({ path, query })`. Handle a non-2xx `response.status`.
- **Check or calculate in the CRM** (eligibility, a quote): a Custom API in `data.actions`, called with `useAction(name).run(inputs)`. The server adds the contact as `ContactId`, so the Custom API must act only for that contact.
- **Nearest office map**: a `screen` slot, `nativeModules: ["expo-location", "react-native-maps"]`, and a readable list as well as the map for screen-reader users.
- **Custom input**: a `field` slot with the right `valueType`. Call `onChange(value)`, show `error`, and use `form.values` (SDK ^0.1.2) when it depends on other answers.

## 4. Get it into the app

Tell the developer:

1. **Upload**: someone at MGCRM opens **Plugins** in Haiko Studio for their organisation and uploads `dist/<id>-<version>.zip`. Studio runs the same validation and shows the result.
2. **Place it** in the app's editor: a widget under **Dashboard widgets → + Add Widget**; a screen under **Screens → + Add Screen → Plugin Screen**; a field on a form field (**Field Type: Plugin**); a step on a workflow step (**Type: Plugin**). Studio shows what it will be allowed to do, in plain words, and they confirm.
3. **Security**: the plugin can only read entities the app's security manifest already links to the contact. If Studio refuses the grants, run `haiko-security` (and publish) first.
4. Studio's **Preview** shows it straight away, with sample data.

Changing it later: bump `version` (a version can't be uploaded twice), pack, upload. Studio offers the app an upgrade.
