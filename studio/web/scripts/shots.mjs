// Screenshot every screen in mock mode against `vite preview` (dev tool; not part of the app).
// Usage: node scripts/shots.mjs <outDir> [baseUrl]
// Logs: whether WebGL is really on (data-gl), console errors, and any request to a non-local host.
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const out = process.argv[2] ?? "shots";
const base = process.argv[3] ?? "http://127.0.0.1:4173";
const only = process.env.SHOTS_ONLY ? process.env.SHOTS_ONLY.split(",") : null;
mkdirSync(out, { recursive: true });

const HOLD = "glow-serum-testimonial";
const SHOTS = [
  { name: "01-home", path: "/" },
  { name: "02-new-edit", path: "/new" },
  { name: "03-live-running", path: "/p/cafe-opening-reel/live", wait: 4000 },
  { name: "04-live-failed", path: "/p/podcast-ep12-clip/live" },
  { name: "05-review-hold", path: `/p/${HOLD}/review`, wait: 3000 },
  { name: "06-review-overlays", path: `/p/${HOLD}/review`, wait: 3000, act: async (page) => {
      await page.getByRole("switch", { name: "Platform UI" }).click();
      await page.getByRole("switch", { name: "Safe zones" }).click();
      await page.getByRole("button", { name: "Play" }).first().click();
      await page.waitForTimeout(2200);
    } },
  { name: "07-layers", path: `/p/${HOLD}/layers`, wait: 3000, act: async (page) => {
      const pi = page.getByRole("button", { name: /^Punch-ins/ }).first();
      if (await pi.count()) await pi.click();
      else await page.getByRole("button", { name: /^Line 4/ }).click();
      await page.waitForTimeout(800);
    } },
  { name: "08-revise", path: `/p/${HOLD}/revise`, act: async (page) => {
      await page.getByRole("textbox", { name: "Paste the client's notes" }).fill("0:01 faster\ngibberish line ??\nlove it\n0:12 spell the brand right");
      await page.getByRole("button", { name: "Preview notes" }).click();
      await page.waitForTimeout(600);
    } },
  { name: "09-adjust", path: `/p/${HOLD}/adjust`, act: async (page) => {
      await page.getByRole("textbox", { name: "Longest pause kept" }).fill("100");
      await page.waitForTimeout(300);
    } },
  { name: "10-deliver", path: `/p/founder-story-cut-1/deliver` },
  { name: "11-libraries", path: "/studio/libraries" },
  { name: "12-brands", path: "/studio/brands" },
  { name: "13-quality", path: "/studio/quality" },
  { name: "14-settings", path: "/studio/settings" },
];

const browser = await chromium.launch({ channel: process.env.SHOTS_CHANNEL ?? "chrome", headless: true, args: ["--enable-gpu", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader"] });
const external = new Set();
const errors = [];

async function session(reducedMotion) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, reducedMotion });
  const page = await ctx.newPage();
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (!["127.0.0.1", "localhost"].includes(u.hostname) && u.protocol.startsWith("http")) external.add(r.url());
  });
  page.on("console", (m) => m.type() === "error" && errors.push(`[${reducedMotion}] ${page.url()}: ${m.text()}`));
  page.on("pageerror", (e) => errors.push(`[${reducedMotion}] ${page.url()}: ${e.message}`));
  return { ctx, page };
}

async function shoot(page, s, suffix = "") {
  await page.goto(base + s.path, { waitUntil: "networkidle" });
  await page.waitForTimeout(s.wait ?? 1500);
  if (s.act) await s.act(page);
  const gl = await page.evaluate(() => [...document.querySelectorAll("[data-gl]")].map((e) => e.getAttribute("data-gl")).join(",") || "none");
  const file = join(out, `${s.name}${suffix}.png`);
  await page.screenshot({ path: file, fullPage: !!s.full });
  console.log(`${file}  gl=${gl}`);
}

{
  const { ctx, page } = await session("no-preference");
  await page.goto(base + "/?mock=1", { waitUntil: "networkidle" });
  for (const s of SHOTS) if (!only || only.includes(s.name)) await shoot(page, s);
  await ctx.close();
}
if (!only || only.includes("reduced")) {
  const { ctx, page } = await session("reduce");
  await page.goto(base + "/?mock=1", { waitUntil: "networkidle" });
  for (const s of SHOTS.filter((x) => ["01-home", "03-live-running", "05-review-hold", "07-layers"].includes(x.name))) await shoot(page, s, "-reduced");
  await ctx.close();
}
if (!only || only.includes("down")) {
  const { ctx, page } = await session("no-preference");
  await page.goto(base + "/?mock=down", { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(out, "15-engine-down.png") });
  console.log(join(out, "15-engine-down.png"));
  await ctx.close();
}

await browser.close();
console.log("external requests:", external.size ? [...external].join("\n  ") : "none");
console.log("console errors:", errors.length ? "\n  " + errors.join("\n  ") : "none");
