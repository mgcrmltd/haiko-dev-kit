#!/usr/bin/env node
/**
 * Zips haiko-plugin.json and src/ into dist/<id>-<version>.zip, the file you
 * upload to Haiko Studio. Validates first, as Studio will.
 */
import { mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const AdmZip = require("adm-zip");
const { validatePlugin } = require("@mgcrm-haiko-builds/plugin-tools");

const report = await validatePlugin(".");
if (!report.valid) {
  console.error("Not packed: fix these first (npm run validate for details).");
  for (const e of report.errors) console.error(`  ${e.code}  ${e.file ?? ""}${e.line ? `:${e.line}` : ""}  ${e.message}`);
  process.exit(1);
}
const manifest = JSON.parse(readFileSync("haiko-plugin.json", "utf8"));
const zip = new AdmZip();
zip.addLocalFile("haiko-plugin.json");
zip.addLocalFolder("src", "src");
mkdirSync("dist", { recursive: true });
const out = `dist/${manifest.id}-${manifest.version}.zip`;
zip.writeZip(out);
console.log(`Packed ${out} (accessibility: ${report.accessibility})`);
