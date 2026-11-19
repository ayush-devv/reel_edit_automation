// Screenshot every screen against the REAL API (`reel studio` on 127.0.0.1:8765) and log every console error and
// failed /api call — the web app ↔ API integration check. Dev tool, not part of the app.
// Each screen is captured top to bottom (the app scrolls inside its main panel, so a full-page shot would miss the
// lower panels): <name>.png, then <name>-2.png, <name>-3.png … Layers also gets a shot with a block selected.
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
const MAX_PAGES = 4;

const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--enable-gpu", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader"] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const problems = [];
page.on("console", (m) => m.type() === "error" && problems.push(`console ${page.url()}: ${m.text()}`));
page.on("pageerror", (e) => problems.push(`pageerror ${page.url()}: ${e.message}`));
page.on("response", (r) => {
  if (r.url().includes("/api/") && r.status() >= 400) problems.push(`HTTP ${r.status()} ${r.request().method()} ${r.url().replace(token, "<token>")}`);
});

/** Scroll the tallest scrollable element (the main panel) one viewport at a time. Returns false at the end. */
const scrollStep = (i) =>
  page.evaluate((i) => {
    const els = [document.scrollingElement, ...document.querySelectorAll("*")].filter((e) => e && e.scrollHeight > e.clientHeight + 4 && getComputedStyle(e).overflowY !== "visible");
    const el = els.sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
    if (!el) return false;
    const target = i * el.clientHeight * 0.9;
    if (target >= el.scrollHeight - el.clientHeight + el.clientHeight * 0.9) return false;
    el.scrollTop = target;
    return true;
  }, i);

await page.goto(`${base}/?token=${token}`, { waitUntil: "networkidle" });
for (const [name, path] of SHOTS) {
  await page.goto(`${base}${path}`, { waitUntil: "networkidle" }).catch((e) => problems.push(`goto ${path}: ${e.message}`));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: join(out, `${name}.png`) });
  for (let i = 1; i < MAX_PAGES && (await scrollStep(i)); i++) {
    await page.waitForTimeout(400);
    await page.screenshot({ path: join(out, `${name}-${i + 1}.png`) });
  }
}

// Layers: flat view, click a punch-in block, read the Editor's reason (AC-8).
await page.goto(`${base}/p/${pid}/layers`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.getByRole("radio", { name: "Flat" }).or(page.getByRole("button", { name: "Flat" })).first().click().catch((e) => problems.push(`layers flat: ${e.message}`));
await page.waitForTimeout(500);
const block = page.locator('button[aria-label^="Punch-ins:"]').first();
if (await block.count()) await block.click();
else await page.locator('button[aria-label^="Source video:"]').first().click().catch((e) => problems.push(`layers click: ${e.message}`));
await page.waitForTimeout(500);
await page.screenshot({ path: join(out, "05-layers-selected.png") });

writeFileSync(join(out, "problems.txt"), problems.join("\n") + (problems.length ? "\n" : ""));
console.log(`${problems.length} problem(s)`);
console.log(problems.slice(0, 60).join("\n"));
await browser.close();
