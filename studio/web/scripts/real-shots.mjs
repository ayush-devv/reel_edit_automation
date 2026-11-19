// Screenshot every screen against the REAL API (`reel studio` on 127.0.0.1:8765) and log every console
// error and failed /api call — the web app ↔ API integration check. Dev tool, not part of the app.
// Usage: node scripts/real-shots.mjs <outDir> <projectId> [baseUrl]
import { chromium } from "playwright";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const out = process.argv[2] ?? "real-shots";
const pid = process.argv[3] ?? "_real_doac";
const base = process.argv[4] ?? "http://127.0.0.1:8765";
const token = readFileSync(join(homedir(), ".config", "reel", "studio_token"), "utf8").trim();
mkdirSync(out, { recursive: true });

const SHOTS = [
  ["01-home", "/"], ["02-new-edit", "/new"], ["03-live", `/p/${pid}/live`], ["04-review", `/p/${pid}/review`],
  ["05-layers", `/p/${pid}/layers`], ["06-revise", `/p/${pid}/revise`], ["07-adjust", `/p/${pid}/adjust`], ["08-deliver", `/p/${pid}/deliver`],
  ["09-libraries", "/studio/libraries"], ["10-brands", "/studio/brands"], ["11-quality", "/studio/quality"], ["12-settings", "/studio/settings"],
];

const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--enable-gpu", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader"] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const problems = [];
page.on("console", (m) => m.type() === "error" && problems.push(`console ${page.url()}: ${m.text()}`));
page.on("pageerror", (e) => problems.push(`pageerror ${page.url()}: ${e.message}`));
page.on("response", (r) => {
  if (r.url().includes("/api/") && r.status() >= 400) problems.push(`HTTP ${r.status()} ${r.request().method()} ${r.url().replace(token, "<token>")}`);
});
await page.goto(`${base}/?token=${token}`, { waitUntil: "networkidle" });
for (const [name, path] of SHOTS) {
  await page.goto(`${base}${path}`, { waitUntil: "networkidle" }).catch((e) => problems.push(`goto ${path}: ${e.message}`));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: join(out, `${name}.png`) });
}
writeFileSync(join(out, "problems.txt"), problems.join("\n") + "\n");
console.log(`${problems.length} problem(s)`);
console.log(problems.slice(0, 60).join("\n"));
await browser.close();
