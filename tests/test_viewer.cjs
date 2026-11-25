// Exercise the shipped HTML, including the actual downloaded-core traces from this CI run.
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const assert = require("node:assert/strict");
const { chromium } = require("playwright-core");

(async () => {
  const browser = await chromium.launch({channel: "chrome", headless: true});
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    const root = process.env.RUNNER_TEMP;
    await page.goto(pathToFileURL(path.join(root, "comparison.html")).href);
    const table = page.locator("#compare-rows tr");
    assert.equal(await table.count(), 2);
    await page.getByLabel("Snes9x", {exact:true}).uncheck();
    assert.equal(await table.count(), 1);
    assert.match(await table.innerText(), /bsnes/);
    await page.getByText("FPS trace", {exact:true}).click();
    assert.match(await page.locator("#build").innerText(), /bsnes /);
    await page.getByText("Back to comparison", {exact:true}).click();
    await page.getByLabel("bsnes", {exact:true}).uncheck();
    assert.equal(await table.count(), 0);
    assert.match(await page.locator("#compare-message").innerText(), /Select an emulator/);
    await page.getByLabel("Game or ROM name", {exact:true}).fill("nonexistent-game");
    assert.equal(await page.locator("#cohort option").count(), 0);

    // Exercise the public issue reader with two matched, one historical and two unmatched records.
    const embedded = JSON.parse(await page.locator("#run-data").textContent());
    const [a,b] = embedded;
    const old = {...a}; delete old.comparison_id;
    const records = [a,b,old,{...a,warmup_frames:a.warmup_frames+1},{...b,comparison_id:"00000000-0000-4000-8000-000000000001"}];
    const issues = records.map((r,i)=>({number:i+1,title:"[Score test]",body:"\x60\x60\x60json\n"+JSON.stringify(r)+"\n\x60\x60\x60"}));
    await page.route("https://api.github.com/**", route => route.fulfill({json:issues}));
    await page.goto(pathToFileURL(path.resolve("dist/scores.html")).href+"#compare");
    await page.getByLabel("Snes9x",{exact:true}).waitFor();
    assert.equal(await page.locator("#cohort option").count(), 3);
    assert.equal(await table.count(), 2);
    await page.getByLabel("Game, device and frame window").selectOption({index:1});
    assert.equal(await table.count(), 1);
    await page.getByText("All published runs", {exact:true}).first().click();
    assert.equal(await page.locator("#rows tr").count(),5);
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
  }
})().catch(err=>{ console.error(err); process.exitCode=1; });
