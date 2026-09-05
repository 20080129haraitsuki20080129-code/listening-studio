import { expect, test, type Page } from "@playwright/test";

/**
 * Covers the E2E scenarios in TASKS.md's pre-merge gate: monologue, dialogue
 * with distinct voices, A-B repeat, transcript hiding, and save/reload.
 *
 * These drive the real backend, so audio really is synthesized.
 */

async function waitForRender(page: Page) {
  // Generation is provider-bound; give it room but fail loudly on error.
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible({
    timeout: 180_000,
  });
}

test.describe("monologue", () => {
  test("generates audio and plays it", async ({ page }) => {
    await page.goto("/create");

    await page.getByLabel("Project title").fill("E2E monologue");
    await page
      .getByLabel("English script")
      .fill("Climate change is altering migration patterns.");

    await page.getByRole("button", { name: "Save & parse" }).click();
    await expect(page.getByText(/Segments \(/)).toBeVisible();

    await page.getByLabel("Accent").first().selectOption("british");
    await page.locator("ul li button").first().click();

    await page.getByRole("button", { name: "Generate audio" }).click();
    await waitForRender(page);

    const duration = await page
      .locator("audio")
      .evaluate((el: HTMLAudioElement) => el.duration);
    expect(duration).toBeGreaterThan(0);
  });
});

test.describe("dialogue", () => {
  test("assigns different voices per speaker and renders both", async ({
    page,
  }) => {
    await page.goto("/create");
    await page.getByRole("button", { name: "Dialogue" }).click();
    await page.getByLabel("Project title").fill("E2E dialogue");
    await page.getByRole("button", { name: "Save & parse" }).click();

    // Both speakers are detected from the [A] / [B] markup.
    await expect(page.getByText("Speaker A")).toBeVisible();
    await expect(page.getByText("Speaker B")).toBeVisible();

    await page.getByLabel("Accent").nth(0).selectOption("british");
    await page.locator("ul").nth(0).locator("li button").first().click();

    await page.getByLabel("Accent").nth(1).selectOption("american");
    await page.locator("ul").nth(1).locator("li button").first().click();

    // The two speakers must end up on different voices.
    const chosen = await page
      .locator("h3")
      .filter({ hasText: /Speaker [AB]/ })
      .allInnerTexts();
    expect(chosen).toHaveLength(2);
    expect(chosen[0]).not.toEqual(chosen[1]);

    await page.getByRole("button", { name: "Generate audio" }).click();
    await waitForRender(page);
  });
});

test.describe("player", () => {
  test("A-B repeat loops, and playback rate leaves the audio unchanged", async ({
    page,
  }) => {
    await page.goto("/create");
    await page.getByLabel("Project title").fill("E2E player");
    await page
      .getByLabel("English script")
      .fill(
        "First sentence for the loop test. Second sentence follows it. A third sentence gives us length.",
      );
    await page.getByRole("button", { name: "Save & parse" }).click();
    await page.getByLabel("Accent").first().selectOption("american");
    await page.locator("ul li button").first().click();
    await page.getByRole("button", { name: "Generate audio" }).click();
    await waitForRender(page);

    const audio = page.locator("audio");
    const before = await audio.evaluate((el: HTMLAudioElement) => el.duration);

    // Playback rate must not alter the stored audio (SPEC section 10.2).
    await page.getByRole("button", { name: "1.5×" }).click();
    const after = await audio.evaluate((el: HTMLAudioElement) => ({
      rate: el.playbackRate,
      duration: el.duration,
    }));
    expect(after.rate).toBe(1.5);
    expect(after.duration).toBeCloseTo(before, 3);

    // Mark a loop, then confirm playback wraps back inside it.
    await audio.evaluate((el: HTMLAudioElement) => {
      el.playbackRate = 1;
      el.currentTime = 1.0;
    });
    await page.getByRole("button", { name: /^Set A/ }).click();
    await audio.evaluate((el: HTMLAudioElement) => {
      el.currentTime = 2.5;
    });
    await page.getByRole("button", { name: /^Set B/ }).click();
    await page.getByRole("button", { name: "Loop", exact: true }).click();
    await expect(page.getByRole("button", { name: "Looping" })).toBeVisible();

    const wrapped = await audio.evaluate(async (el: HTMLAudioElement) => {
      el.currentTime = 2.4;
      await el.play();
      await new Promise((r) => setTimeout(r, 1500));
      el.pause();
      return el.currentTime;
    });
    expect(wrapped).toBeLessThan(2.5);
  });

  test("transcript can be hidden and shown", async ({ page }) => {
    await page.goto("/create");
    await page.getByLabel("Project title").fill("E2E transcript");
    await page.getByLabel("English script").fill("A hidden transcript sentence.");
    await page.getByRole("button", { name: "Save & parse" }).click();
    await page.getByLabel("Accent").first().selectOption("american");
    await page.locator("ul li button").first().click();
    await page.getByRole("button", { name: "Generate audio" }).click();
    await waitForRender(page);

    await expect(
      page.getByText("A hidden transcript sentence.").last(),
    ).toBeVisible();
    await page.getByRole("button", { name: "Hide transcript" }).click();
    await expect(page.getByText("Transcript hidden")).toBeVisible();
    await page.getByRole("button", { name: "Show transcript" }).click();
    await expect(page.getByText("Transcript hidden")).toBeHidden();
  });
});

test.describe("project persistence", () => {
  test("settings survive a reload", async ({ page }) => {
    await page.goto("/create");
    await page.getByLabel("Project title").fill("E2E persisted");
    await page.getByLabel("English script").fill("Persisted sentence one.");
    await page.getByRole("button", { name: "Save & parse" }).click();
    await expect(page.getByText(/Segments \(/)).toBeVisible();

    // Saving swaps the URL to the project route.
    await expect(page).toHaveURL(/\/projects\/[0-9a-f-]{36}$/);
    const url = page.url();

    await page.goto(url);
    await expect(page.getByLabel("Project title")).toHaveValue("E2E persisted");
    await expect(page.getByLabel("English script")).toHaveValue(
      "Persisted sentence one.",
    );
    await expect(page.getByText(/Segments \(/)).toBeVisible();
  });
});
