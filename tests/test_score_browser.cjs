// Exercise the shipped score browser against its worker and an isolated SQLite database.
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const { once } = require("node:events");
const { createInterface } = require("node:readline");
const { chromium, firefox, webkit } = require("playwright-core");
const axe = require("axe-core");

async function run() {
  const name = process.argv[3] || "chrome";
  const engine = {chrome: chromium, firefox, webkit}[name];
  const server = spawn(process.execPath, ["--experimental-sqlite", "tests/local_api.mjs", process.argv[2]],
    {stdio: ["ignore", "pipe", "inherit"]});
  let browser;
  try {
    const output = createInterface({input: server.stdout});
    const [root] = await once(output, "line");
    assert.match(root, /^http:\/\/127\.0\.0\.1:\d+$/);
    browser = await engine.launch(name === "chrome" ? {channel: "chrome"} : {});
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    async function visit(route) {
      await page.goto(root + route);
      await page.waitForFunction(() => document.getElementById("status")?.innerText !== "Loading scores…");
      await page.evaluate(() => document.fonts.ready);
    }
    const sample = "00000000-0000-4000-8000-000000000004";
    const routes = ["/", "/compare?q=Super+Mario+World&demo=1", "/rankings?demo=1", "/history?demo=1",
      "/library", "/method", "/run/" + sample + "?demo=1", "/campaign/" + sample, "/?q=missing"];
    for (const width of [1280, 768, 390, 320]) {
      await page.setViewportSize({width, height: 820});
      for (const route of routes) {
        await visit(route);
        assert.equal(await page.locator("#status").innerText(), "", route);
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), width + " " + route);
        if (name === "chrome" && width === 1280) {
          const violations = await page.evaluate(axe.source + `; axe.run(document,{runOnly:{type:"tag",
            values:["wcag2a","wcag2aa","wcag21aa","wcag22aa"]}}).then(r=>r.violations.map(v=>v.id))`);
          assert.deepEqual(violations, [], route);
        }
      }
    }
    await page.goto(root + "/");
    await page.getByRole("link", {name: "Downloads", exact: true}).click();
    await page.waitForURL("**/download");
    for (const width of [1280, 390, 320]) {
      await page.setViewportSize({width, height: 820});
      for (const [label, platform, count] of [["Mac app", "mac", 2], ["Windows app", "windows", 2], ["Command line", "cli", 6]]) {
        await page.getByRole("group", {name: "Choose a download"}).getByRole("link", {name: new RegExp(label)}).click();
        await page.waitForURL("**/download?platform=" + platform);
        const files = page.locator(".install-panel .file-link");
        assert.equal(await files.count(), count);
        for (const url of await files.evaluateAll(links => links.map(link => link.href))) {
          assert.match(url, /^https:\/\/github\.com\/MrCTO13\/EmuBench\/releases\/download\/v[\w.-]+\/[\w.-]+\.zip$/);
        }
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), width + " " + platform);
        if (name === "chrome" && width === 1280) {
          const violations = await page.evaluate(axe.source + `; axe.run(document,{runOnly:{type:"tag",
            values:["wcag2a","wcag2aa","wcag21aa","wcag22aa"]}}).then(r=>r.violations.map(v=>v.id))`);
          assert.deepEqual(violations, [], platform);
        }
      }
    }
    await visit("/?demo=1");
    await page.getByLabel("Game or ROM name").fill("Super Mario World");
    await page.getByRole("button", {name: "Search", exact: true}).click();
    await page.waitForURL(/q=Super/);
    await page.getByRole("button", {name: "Compare selected emulators"}).click();
    await page.waitForURL(/compare/);
    assert.equal(await page.locator("fieldset label:visible").count(), 3);
    const peer = page.getByRole("checkbox", {name: "Snes9x", exact: true});
    await peer.uncheck();
    assert.equal(await page.locator("tbody tr").filter({hasText: "Snes9x"}).count(), 0);
    await peer.check();
    await page.getByRole("link", {name: "Super Mario World (USA)", exact: true}).first().click();
    const cursor = page.getByRole("slider");
    await cursor.focus();
    await cursor.press("End");
    const end = await cursor.inputValue();
    await cursor.press("Home");
    assert.notEqual(await cursor.inputValue(), end);
    await visit("/library");
    await page.getByRole("combobox", {name: "Console", exact: true}).selectOption("Nintendo 64");
    assert.equal(await page.locator("tbody tr").count(), 1);
    assert.match(await page.locator("tbody").innerText(), /Final Cartasy/);
    await visit("/rankings?demo=1");
    await page.getByText("See the 24 selected games").click();
    assert.equal(await page.locator("#results details tbody tr").count(), 24);
    await visit("/run/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    assert.match(await page.locator("#status").innerText(), /could not be found/);
    assert.deepEqual(errors, []);
    console.log(name + " passed 36 page/viewport combinations and the interactive score browser checks.");
  } finally {
    server.kill();
    if (browser) await browser.close();
  }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
