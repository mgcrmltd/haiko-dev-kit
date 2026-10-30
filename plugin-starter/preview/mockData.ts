import { createMockHost } from "@mgcrm-haiko-builds/plugin-sdk";

/**
 * In-memory data for the preview and the tests. Only the signed-in contact's
 * rows: the real API scopes to the contact, the mock does not.
 */
export function makeHost() {
  return createMockHost({
    pluginId: "com.example.my-plugin",
    contact: { firstName: "Alex" },
    config: { heading: "My open cases", screenId: "cases" },
    tables: {
      incident: [
        { id: "1", title: "Leaking tap", statecode: 0 },
        { id: "2", title: "Broken window", statecode: 0 },
        { id: "3", title: "Fixed: fence panel", statecode: 1 },
      ],
    },
    latencyMs: 400,
  });
}
