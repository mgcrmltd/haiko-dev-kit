# Haiko Plugin Author Guide

> Reference for the `haiko-plugins` skill, copied from Haiko's Plugin Author Guide. Where it says MGCRM, that's the team behind Haiko.

Everything you need to write a Haiko plugin, test it, and get it into a customer's app. You shouldn't need to read Haiko's source; if you do, that's a gap in this page, so please say so.


# What a plugin is

A plugin is a React Native component that Haiko compiles into a customer's app, in one of four **slots**:

| Slot kind | Where it appears | Props it gets |
|---|---|---|
| `screen` | A whole page. Navigation items, dashboard cards and journey actions can open it. | `config` |
| `widget` | A card on the dashboard, below the configured cards. Draw the whole card, including its own heading (`accessibilityRole="header"`). | `config`, `openScreen(screenId)` |
| `field` | An input in a form, wizard or progress-tracker stage. The form shows the label, the required marker and the error; you render only the input. | `config`, `value`, `onChange`, `onBlur`, `label`, `required`, `disabled`, `error`, `reportError`, `form` (SDK 0.1.2+) |
| `step` | A whole step of a wizard | `config`, `values`, `setValues`, `registerValidate` |

The people using the app are an organisation's **contacts**: customers, tenants, students, patients. Everything a plugin reads or writes is the signed-in contact's own data, enforced by the customer's Haiko API, not by your code.

How a plugin gets to a phone:

1. You build it from the **starter**, test it against mock data, and pack it into a zip.
2. MGCRM uploads the zip to the customer's organisation in **Haiko Studio**. Studio validates it; a version that fails is kept with its report but can't be used.
3. The customer's CRM developer **places** it in an app in Studio's editor, sets its settings, and confirms what it may do (its **grants**).
4. Studio compiles it into the app's build. Data access is granted on the customer's Haiko API at the same time.

Plugins are built in, not downloaded at runtime: no plugin code runs that wasn't validated, and every version that ships is fixed (Studio checks each zip's SHA-256 before a build).

# Get started

You need Node 20+, the iOS Simulator or an Android emulator with Expo Go, and `NPM_TOKEN` set to a GitHub token with `read:packages` (Haiko's packages are private, on GitHub Packages under `@mgcrm-haiko-builds`).

Copy the **plugin starter** (`plugin-starter/` in this kit) to a new folder, then:

```bash
npm install
npm start          # press i for the iOS Simulator; the preview has a tab per slot
```

The starter has one sample of each slot in `src/index.tsx`, a preview app (`preview/`) that runs them against mock data, Jest tests (`__tests__/`), and these scripts:

```bash
npm test           # Jest, against MockHaikoHost
npm run typecheck
npm run validate   # the checks Studio runs on upload (codes below)
npm run pack       # validates, then writes dist/<id>-<version>.zip to upload
```

To make it yours:

1. In `haiko-plugin.json` set `id`, `displayName` and `author`. Delete the slots you don't need from the manifest and `src/index.tsx`, and also from `preview/App.tsx` and `__tests__/plugin.test.tsx`, which import every sample (typecheck fails until you do).
2. Write your components in `src/`. `src/index.tsx` (or `.ts`) must export one component per slot, under the name the slot's `export` gives.
3. Declare every entity, column, write, Custom API, outside service and native module you use (see [The manifest](#the-manifest)). Anything undeclared is refused when the app runs.
4. Put sample rows for your entities in `preview/mockData.ts` for the preview. Tests can import them from there or build their own (see Testing below).

Two worked examples (ask MGCRM for a copy if you don't have the Haiko repo): `haiko-plugin-sdk/examples/hello` (CRM reads, a write, a Custom API, a proxy, all four slots) and `haiko-plugin-sdk/examples/offices-map` (self-contained, native modules, no CRM).

# The manifest

`haiko-plugin.json`, at the root of the package:

```json
{
  "id": "com.acme.nearest-office",
  "version": "1.0.0",
  "displayName": "Nearest office",
  "description": "Shows the contact's nearest office.",
  "author": "Acme Ltd",
  "sdk": "^0.1.0",
  "slots": [
    {
      "kind": "widget",
      "export": "NearestOfficeWidget",
      "name": "Nearest office",
      "config": [
        { "key": "screenId", "label": "Screen to open", "type": "string" },
        { "key": "units", "label": "Distances in", "type": "select", "default": "mi",
          "options": [{ "value": "mi", "label": "Miles" }, { "value": "km", "label": "Kilometres" }] }
      ]
    }
  ],
  "data": {
    "read": { "incident": ["title", "statecode"] },
    "write": [{ "name": "logVisit", "entity": "incident", "op": "create", "columns": ["title", "description"] }],
    "actions": ["acme_CheckEligibility"]
  },
  "proxies": [{ "id": "postcodes", "baseUrl": "https://api.postcodes.io" }],
  "externalHosts": ["tiles.example.com"],
  "nativeModules": ["expo-location"]
}
```

| Key | Rules |
|---|---|
| `id` | Lowercase reverse-DNS, e.g. `com.acme.nearest-office`. Never changes: it's how apps refer to the plugin. |
| `version` | Semver, e.g. `1.0.0` or `1.1.0-beta.1`. Bump it for every upload; a version can't be uploaded twice. |
| `displayName`, `description`, `author` | Shown to the CRM developer in Studio. |
| `sdk` | The `@mgcrm-haiko-builds/plugin-sdk` range you built against, e.g. `^0.1.0`. Must include the SDK Haiko builds apps with today. |
| `slots[]` | At least one. `kind`: `screen`, `widget`, `field` or `step`. `export`: the component's export name (each used once). `name`: what the CRM developer sees. Field slots also need `valueType`: `string`, `number`, `boolean` or `object`. |
| `slots[].config[]` | Settings the CRM developer fills in when placing the slot. `key` (an identifier), `label`, `type` (`string`, `number`, `boolean`, `select`), optional `required`, `default`, `help`; a `select` needs `options` of `{ value, label }`. |
| `data.read` | Entity → columns you read, all lowercase logical names. |
| `data.write[]` | Each write you make: `name` (what you pass to `useSubmit`), `entity`, `op` (`create` or `update`) and exactly the `columns` written. |
| `data.actions[]` | D365 Custom API (or action) names you call. |
| `proxies[]` | Outside services called through the customer's Haiko API: `id` and an `https://` `baseUrl`. |
| `externalHosts[]` | Hosts the phone calls directly (no keys). Lowercase host names only, e.g. `api.postcodes.io`. |
| `nativeModules[]` | Native modules you import, from the [allowlist](#native-modules). |

# The SDK

Import everything from `@mgcrm-haiko-builds/plugin-sdk`. Your component is rendered inside a host that Haiko provides; the hooks read from it.

```tsx
import { useQuery, useTheme, type WidgetSlotProps } from "@mgcrm-haiko-builds/plugin-sdk";

type Config = { screenId?: string };

export function OpenCasesWidget({ config, openScreen }: WidgetSlotProps<Config>) {
  const theme = useTheme();
  const { rows, loading, error } = useQuery({
    entity: "incident",
    columns: ["title"],
    where: [{ attribute: "statecode", operator: "eq", value: 0 }],
  });
  // ...render, using theme colours; see the accessibility checklist
}
```

**A field's context.** From plugin SDK 0.1.2 a field also gets `form`, read-only: `form.values` (the other answers on the same form or stage, by field name), `form.entity` and `form.recordId` (the record being edited, or `null` while one is being created). Use it when your field depends on something else, e.g. the advisor chosen earlier or the record you're on. Set `"sdk": "^0.1.2"` in your manifest if you use it. It's optional in the types, so check it's there.

Settings arrive as the plain values set in Studio (`string`, `number` or `boolean`), so type them that way and narrow them yourself (a `select` arrives as a `string`). Studio fills in a setting's `default` when the slot is placed, but the CRM developer can clear it, and a setting that isn't `required` may be missing: always have a fallback in code.

| Hook | Returns | Notes |
|---|---|---|
| `useContact()` | `{ id, firstName?, lastName?, email? }` | The signed-in contact. |
| `useTheme()` | `primaryColor`, `onPrimaryColor`, `backgroundColor`, `surfaceColor`, `textColor`, `textMutedColor`, `errorColor`, `successColor`, `warningColor`, `borderRadius`, `fontFamily?` | Use these, not your own colours, so the plugin matches the app. |
| `usePluginConfig()` | The slot's settings | Same as the `config` prop. |
| `useNavigation()` | `goBack()`, `canGoBack()`, `openScreen(screenId)` | `openScreen` takes a Studio screen id; a plugin can't leave the app's structure. |
| `useQuery({ entity, columns, where?, orderBy?, top? })` | `{ rows, loading, error, refresh }` | Only the contact's own rows. `where` is a list of `{ attribute, operator, value }`, ANDed; operators `eq`, `ne`, `gt`, `ge`, `lt`, `le`, `in` (value is a list), `like` (`%` wildcards), `null`, `not-null`. No OR, no joins. `orderBy` is `{ attribute, descending? }` (ascending by default); `top` limits the rows. Pass `null` to wait. |
| `useRecord({ entity, id, columns })` | `{ record, loading, error, refresh }` | 403 if the row isn't the contact's. |
| `useSubmit(writeName)` | `{ submit(values, recordId?), submitting, error, result }` | A write from `data.write`. Pass `recordId` for an `update`. Only the declared columns are written. |
| `useAction(name)` | `{ run(inputs), running, error, result }` | A Custom API from `data.actions`. The server adds the contact as the `ContactId` parameter; you can't set it. |
| `useProxy(proxyId)` | `{ request({ path, method?, query?, body? }), loading, error, response }` | A service from `proxies`, called through the Haiko API. A non-2xx status resolves with `response.status`; only failures to call reject. |

Rows come back as the runtime API returns them: lookups are `{ id, name, entity }`, option sets are numbers, and dates and times are ISO 8601 strings (e.g. `2026-10-21T09:30:00.0000000Z`); compare against an ISO string too.

**Declare every column you use**, in `columns`, `where` or `orderBy`, in `data.read`.

**Keep requests stable.** Hooks compare requests by value, so writing the request inline is fine. But a value that changes on every render refetches on every render: work out "now" once, e.g. `const [now] = useState(() => new Date().toISOString())`, and filter with `{ attribute: "scheduledstart", operator: "ge", value: now }`.

**Errors.** Every data call throws (or sets `error` to) a `PluginError`. If `error.userMessage` is set, the CRM wrote it for the contact (a Custom API's message, say): show it as it is. Otherwise show something general, and never show `error.message`.

**If your component throws**, the slot catches it and shows "This feature isn't available right now." with a Try again button, and the rest of the app carries on. Throwing is the right response to a misconfiguration (a setting that can't be read); don't show half a feature.

**Testing.** Render a slot in Jest inside `<MockHaikoHost host={createMockHost({...})}>`. `createMockHost` options, all optional:

| Option | |
|---|---|
| `tables` | Entity → rows, or a `PluginError` to make reads fail, e.g. `new PluginError("down", { userMessage: "Cases are unavailable today." })` |
| `writes` | Write name → `{ entity, op }`, as in your manifest |
| `actions` | Custom API name → function of the inputs, returning the outputs (throw a `PluginError` to test a rejection) |
| `proxies` | Proxy id → function of the request, returning `{ status, body }` |
| `contact`, `theme`, `config`, `pluginId` | Override the defaults |
| `latencyMs` | Delay every call, to see loading states |

The starter's `__tests__/plugin.test.tsx` shows each slot.

# Data access and what the CRM developer sees

Your manifest's `data`, `proxies` and `externalHosts` are a request. When the CRM developer adds your plugin to an app, Studio shows it to them in plain language, for example:

> Enable Nearest office?
> - Read the contact's own incident records: title, statecode
> - Create the contact's own incident records, setting only: title, description
> - Run the CRM action acme_CheckEligibility for the contact
> - Call api.postcodes.io through your Haiko API, with a key kept on your server
> - Send data from the phone to tiles.example.com

They have to confirm before it's added, and again when an upgrade changes the list. Then Studio adds exactly those permissions to the app's security manifest on the customer's Haiko API, and takes them away when the last placement of your plugin is removed.

The rules, enforced by the API whatever your code does:

- **Reads** are always the contact's own rows. An entity can be read only if the customer's security setup already links it to a contact (a contact field such as `customerid`). An entity shared with everyone (no contact field, read by all) can be read too.
- **Writes** need an entity with a contact field, and only the declared columns are written. Each write becomes its own endpoint, `plugin:<your id>:write:<name>`.
- **Custom APIs** get the contact injected as `ContactId`. Write them to act only for that contact.
- **Columns, writes and actions you didn't declare are refused** with an error, at runtime.
- If the customer's setup can't support a grant (an entity with no access rules yet, say), Studio says why and won't let the plugin be added until it's fixed in Security.

**Outside services.** Prefer `proxies` for anything that needs a key: the call goes through the customer's Haiko API and the key stays in the customer's Key Vault, never in the app. Use `externalHosts` only for keyless services the phone can call directly (map tiles, a public lookup). Today Studio publishes a proxy with its id and base URL only; if your service needs a key, tell MGCRM which header it goes in, and they'll set it up on the customer's API.

# Native modules

A plugin can't bring native code. It may import only `react`, `react-native`, `@mgcrm-haiko-builds/plugin-sdk`, its own files in `src/`, and these native modules, declared in `nativeModules`:

| Module | Version (Expo SDK 54) | Notes |
|---|---|---|
| `expo-location` | ~19.0.8 | The app only ever asks while in use. The prompt says: "Your location is used to show what's near you, such as your nearest office. It is only used while you use the app." |
| `react-native-maps` | 1.20.1 | iOS uses Apple Maps. Android needs a Google Maps API key in the app's config: tell MGCRM. |
| `expo-camera` | ~17.0.10 | "The camera is used to take photos you choose to send." No microphone. |
| `expo-haptics` | ~15.0.8 | |
| `expo-image-picker` | ~17.0.11 | Already in every app. "Your photos are used only when you choose one to send." No microphone. |
| `react-native-webview` | 13.15.0 | Already in every app. |

A module is added to an app's build only when one of its plugins declares it, so apps don't carry permission prompts they don't use. The wording of every prompt is fixed by Haiko; you can't change it. Adding a module the app's installed version doesn't have means a full app build rather than an over-the-air update; Studio works that out.

Need another module? Ask MGCRM: it has to be vetted, pinned to the Expo SDK, and given plain-English permission wording.

# Accessibility checklist

Customer apps must meet WCAG 2.2 AA, so the validator checks the most common mistakes and refuses the package if it finds them ([HP060](#hp060)–[HP062](#hp062)). The rest is on you:

- Every `TouchableOpacity`, `TouchableHighlight`, `TouchableWithoutFeedback`, `Pressable`, `TextInput` and `Switch` has an `accessibilityLabel`: what a screen reader says, including state (e.g. "Postcode, required").
- Every touchable has an `accessibilityRole` (`button`, `link`, `tab`, `radio`, `switch`, ...) and an `accessibilityHint` saying what happens ("Double tap to open your cases").
- Dynamic state goes in `accessibilityState`: `{ selected, disabled, checked, expanded, busy }`.
- Errors: `accessibilityRole="alert"` with `accessibilityLiveRegion="assertive"`. Loading and status changes: `accessibilityLiveRegion="polite"`.
- Headings: `accessibilityRole="header"`.
- Never `allowFontScaling={false}`; text must grow with the contact's font size setting.
- Touch targets at least 44×44 (iOS) / 48×48 (Android): `minHeight: 48` on buttons.
- Contrast: 4.5:1 for text, 3:1 for borders of interactive elements (use `#9CA3AF` on white, not lighter). Use the theme's colours.
- A visible focus ring: track `onFocus`/`onBlur` and draw a 2px `#1A73E8` border while focused.
- Anything visual needs another way in. A map, for example, needs a list a screen reader can read (`AccessibilityInfo.isScreenReaderEnabled()` can choose it for them).
- A wizard step that changes moves focus to its heading.

# Versions and upgrades

- Every upload is a new `version`. Versions can't be replaced or deleted, so a version that's in an app is exactly what was validated.
- An app uses one version of your plugin everywhere it's placed. When a newer version passes, Studio offers the CRM developer an upgrade; if its grants differ, they review them again.
- A change that only touches your JavaScript can reach installed apps as an over-the-air update. A new native module needs a full build. Studio decides which.
- When Haiko moves to a new plugin SDK major or Expo SDK, MGCRM re-checks every stored version. Versions built for the old SDK, or that fail the new checks, are marked "Can't be built now" in Studio, and apps that use them can't be built until a fixed version is uploaded and the app is upgraded to it.

# Upload and placement

**Upload** (MGCRM staff, for now). In Studio open **Plugins** for the customer's organisation, choose the zip from `npm run pack`, and upload. Studio validates it with the same checks as `npm run validate` and shows the result. A failed version is kept with its report, so you can see why.

**Placement** (the CRM developer), in the app's editor:

| To place a | Go to |
|---|---|
| screen | **Screens** → **+ Add Screen** → **Plugin Screen** |
| field | a form screen → a field → **Field Type: Plugin** |
| wizard step | **Workflows** → a workflow → a step → **Type: Plugin** |
| dashboard widget | **Dashboard widgets** → **+ Add Widget** |

The picker lists only plugins with a slot of that kind, and only versions that can be built today. The first time a plugin is added they choose its version (newest by default) and confirm its grants; then they fill in its settings. Plugin screens can be targets of navigation items and journey actions like any other screen. Removing the last placement removes the plugin from the app, and its grants with it.

# Validator errors and fixes

`npm run validate` (and Studio's upload) report these codes. Errors stop the package being used; warnings don't.

#### HP001
**The manifest is missing or invalid.** `haiko-plugin.json` must be at the package root, be valid JSON, and follow [The manifest](#the-manifest). The message names the key, e.g. `slots[0].valueType: Field slots need a valueType`.

#### HP002
**Unsafe path in the package.** The zip contains a path that leaves the package (`..`, an absolute path). Pack with `npm run pack`, which zips only `haiko-plugin.json` and `src/`.

#### HP003
**SDK range not supported.** Your `sdk` range doesn't include the plugin SDK Haiko builds with today. Install the current `@mgcrm-haiko-builds/plugin-sdk`, fix any type errors, and set `sdk` to its range (e.g. `^0.1.0`).

#### HP010
**TypeScript error.** Your source doesn't compile in strict mode against the SDK and React Native types. `npm run typecheck` shows the same errors.

#### HP020
**Import not allowed.** You imported something other than `react`, `react-native`, `@mgcrm-haiko-builds/plugin-sdk`, your own files in `src/`, or a module you declared in `nativeModules`. Use the SDK instead of networking or storage libraries; ask MGCRM about anything else ([Native modules](#native-modules)).

#### HP021
**Dynamic require or import.** `require(x)` and `import(x)` must name a module as a plain string, so the validator can check it.

#### HP022
**eval or new Function.** Not allowed: code that writes code can't be checked.

#### HP030
**Source too large.** The source in `src/` is over 500 KB. Move data out (into the slot's settings, or the CRM) and remove unused code.

#### HP040
**No entry file.** `src/index.ts` or `src/index.tsx` is required, exporting one component per slot.

#### HP041
**A slot's export is missing.** A slot's `export` names something `src/index.tsx` doesn't export. Export it by that name, or fix the name in the manifest.

#### HP050
**Fetch to an undeclared host** (warning). You `fetch` a host that isn't in `externalHosts`. Add it, or better, call it through a proxy ([Data access](#data-access-and-what-the-crm-developer-sees)). Declared hosts are what the CRM developer is shown and agrees to; calling a host you didn't declare breaks that promise.

#### HP060
**An interactive element has no `accessibilityLabel`.** Every touchable, `TextInput` and `Switch` needs one: what a screen reader says, including state such as "required". Fails the accessibility gate. See the [checklist](#accessibility-checklist).

#### HP061
**A touchable has no `accessibilityRole`.** Add `button`, `link`, `tab`, `radio`, `switch`, etc. Fails the accessibility gate.

#### HP062
**`allowFontScaling={false}`.** Remove it: text must grow with the contact's font size setting. Fails the accessibility gate.

#### HP063
**A touchable has no `accessibilityHint`** (warning). Add one that says what happens, e.g. "Double tap to submit".

The validator also follows renamed imports (`import { Pressable as Tap } from "react-native"` is still checked as a `Pressable`).

# Related

- 
- The SDK's own README, in `node_modules/@mgcrm-haiko-builds/plugin-sdk/README.md` once you've installed the starter.
