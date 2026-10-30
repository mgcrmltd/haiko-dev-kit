# Haiko plugin starter

A plugin is a React Native component that Haiko compiles into a customer's app in a fixed slot: a **screen**, a dashboard **widget**, a form **field** or a wizard **step**. This project has one sample of each, a preview app that runs them against mock data in Expo Go, tests, and the scripts to check and package your plugin for Haiko Studio.

The full guide: ADO wiki **Plugin Author Guide**. Design and rules: **Architecture / Plugins**. SDK reference and the accessibility checklist: the `@mgcrm-haiko-builds/plugin-sdk` README.

## Start

You need Node 20+, the iOS Simulator or an Android emulator with Expo Go, and `NPM_TOKEN` set to a GitHub token with `read:packages` (the Haiko packages are private).

```bash
npm install
npm start          # press i for the iOS Simulator; the preview has a tab per slot
```

## Make it yours

1. In `haiko-plugin.json`, set `id` (reverse-DNS, never changes), `displayName` and `author`.
2. Edit `src/index.tsx`. Keep one named export per slot listed in `haiko-plugin.json`; delete slots you don't need from both, and from `preview/App.tsx` and `__tests__/plugin.test.tsx`.
3. Declare every CRM entity and column you read (`data.read`), every write (`data.write`), every Custom API (`data.actions`), every outside service (`proxies` or `externalHosts`) and native module (`nativeModules`). Anything undeclared is refused at runtime.
4. Put sample rows for your entities in `preview/mockData.ts`.

## Check and package

```bash
npm test           # Jest, against MockHaikoHost
npm run typecheck
npm run validate   # the same checks Studio runs on upload (errors HP001-HP063)
npm run pack       # validates, then writes dist/<id>-<version>.zip to upload to Studio
```

Bump `version` in `haiko-plugin.json` for every upload; versions are immutable.
