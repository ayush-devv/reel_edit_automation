// Dev probe: what's mounted on a page (canvases, data-gl markers) after it settles.
import { chromium } from "playwright";
const base = process.argv[2] ?? "http://127.0.0.1:4173";
const path = process.argv[3] ?? "/";
const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--enable-gpu", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("console", (m) => console.log("console:", m.type(), m.text()));
await page.goto(base + "/?mock=1", { waitUntil: "networkidle" });
await page.goto(base + path, { waitUntil: "networkidle" });
await page.waitForTimeout(3000);
console.log(
  await page.evaluate(() => ({
    canvases: document.querySelectorAll("canvas").length,
    gl: [...document.querySelectorAll("[data-gl]")].map((e) => e.getAttribute("data-gl")),
    webgl: !!document.createElement("canvas").getContext("webgl2"),
    reduced: matchMedia("(prefers-reduced-motion: reduce)").matches,
  })),
);
await browser.close();
