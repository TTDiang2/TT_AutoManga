/* Render docs/video/index.html frame by frame with headless Edge, then mux
   with ffmpeg. Usage:
     node build.mjs [--fps 24] [--out ../../docs/assets/demo.mp4]
   Requires: puppeteer-core (`npm i puppeteer-core` next to this script or in
   a parent node_modules), Edge/Chrome, ffmpeg on PATH.
   Technique after lemo-opuscar/TECHNIQUE.md (picture = render(t), sampled). */
import puppeteer from "puppeteer-core";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import url from "node:url";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const arg = (name, dflt) => {
  const i = process.argv.indexOf(name);
  return i > -1 ? process.argv[i + 1] : dflt;
};
const FPS = parseInt(arg("--fps", "24"), 10);
const OUT = path.resolve(HERE, arg("--out", "../../docs/assets/demo.mp4"));
const FRAMES = path.join(HERE, "out");
const DUR = 78;

const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const browser = await puppeteer.launch({
  executablePath: EDGE,
  headless: "new",
  args: ["--disable-gpu", "--hide-scrollbars", "--font-render-hinting=none"],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 1 },
});
const page = await browser.newPage();
await page.goto("file:///" + path.join(HERE, "index.html").replace(/\\/g, "/"), {
  waitUntil: "networkidle2",
});
// every image must be decoded before frame sampling, or frames tear
await page.waitForFunction("window.READY && window.READY() === true", { timeout: 60000 });
await page.evaluate(() => document.fonts.ready);

fs.mkdirSync(FRAMES, { recursive: true });
const total = Math.round(DUR * FPS);
console.log(`rendering ${total} frames @ ${FPS}fps -> ${FRAMES}`);
for (let f = 0; f < total; f++) {
  const t = f / FPS;
  await page.evaluate(tt => window.render(tt), t);
  await page.screenshot({
    path: path.join(FRAMES, `f${String(f).padStart(5, "0")}.png`),
    omitBackground: false,
  });
  if (f % 120 === 0) console.log(`  frame ${f}/${total} (t=${t.toFixed(1)}s)`);
}
await browser.close();

fs.mkdirSync(path.dirname(OUT), { recursive: true });
execFileSync("ffmpeg", [
  "-y", "-framerate", String(FPS), "-i", path.join(FRAMES, "f%05d.png"),
  "-c:v", "libx264", "-preset", "slow", "-crf", "20",
  "-pix_fmt", "yuv420p", "-movflags", "+faststart", OUT,
], { stdio: ["ignore", "ignore", "inherit"] });
console.log("wrote", OUT, Math.round(fs.statSync(OUT).size / 1024), "KB");
