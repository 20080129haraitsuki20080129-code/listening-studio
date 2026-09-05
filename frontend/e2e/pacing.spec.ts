import { expect, test } from "@playwright/test";

test.use({ locale: "en-US" });

test.describe("speed levels", () => {
  test("seven levels, each labelled by a words-per-minute band", async ({
    page,
  }) => {
    await page.goto("/create");
    const slider = page.getByLabel("Speed");
    await expect(slider).toHaveAttribute("min", "1");
    await expect(slider).toHaveAttribute("max", "7");

    // A bare multiplier says nothing about pace; a band is something you can
    // aim at.
    await expect(page.getByText(/Level 4 · about 140-150 words\/min/)).toBeVisible();

    await slider.fill("1");
    await expect(page.getByText(/Level 1 · about 95-105 words\/min/)).toBeVisible();

    await slider.fill("7");
    await expect(page.getByText(/Level 7 · about 170-185 words\/min/)).toBeVisible();
  });

  test("the chosen level survives a reload", async ({ page }) => {
    await page.goto("/create");
    await page.getByLabel("Project title").fill("Pace");
    await page.getByLabel("English script").fill("One sentence here.");
    await page.getByLabel("Speed").fill("2");
    await page.getByRole("button", { name: "Save & parse" }).click();
    await expect(page.getByText(/Segments \(/)).toBeVisible();

    await page.reload();
    await expect(page.getByText(/Level 2 · about 105-125 words\/min/)).toBeVisible();
  });
});

test.describe("word count", () => {
  test("totals and per-segment counts are shown", async ({ page }) => {
    await page.goto("/create");
    await page.getByLabel("Project title").fill("Counting");
    await page.getByLabel("English script").fill("One two three. Four five.");
    await page.getByRole("button", { name: "Save & parse" }).click();

    await expect(page.getByText("5 words")).toBeVisible();
    await expect(page.getByText("3 words")).toBeVisible();
    await expect(page.getByText("2 words")).toBeVisible();
  });
});

test.describe("repeat", () => {
  test("the gap only applies once the passage repeats", async ({ page }) => {
    await page.goto("/create");
    // A gap between hearings is meaningless when there is only one hearing.
    await expect(page.getByLabel("Gap between repeats")).toBeDisabled();

    await page.getByLabel("Repeat the passage").selectOption("2");
    await expect(page.getByLabel("Gap between repeats")).toBeEnabled();
  });

  test("repeat settings persist across a reload", async ({ page }) => {
    await page.goto("/create");
    await page.getByLabel("Project title").fill("Repeat");
    await page.getByLabel("English script").fill("One sentence here.");
    await page.getByLabel("Repeat the passage").selectOption("3");
    await page.getByLabel("Gap between repeats").selectOption("5000");
    await page.getByRole("button", { name: "Save & parse" }).click();
    await expect(page.getByText(/Segments \(/)).toBeVisible();

    await page.reload();
    await expect(page.getByLabel("Repeat the passage")).toHaveValue("3");
    await expect(page.getByLabel("Gap between repeats")).toHaveValue("5000");
  });

  test("repeating makes the rendered audio longer", async ({ page }) => {
    const durationFor = async (repeats: string) => {
      await page.goto("/create");
      await page.getByLabel("Project title").fill(`Repeat ${repeats}`);
      await page.getByLabel("English script").fill("A short passage to repeat.");
      await page.getByLabel("Repeat the passage").selectOption(repeats);
      if (repeats !== "1") {
        await page.getByLabel("Gap between repeats").selectOption("1000");
      }
      await page.getByRole("button", { name: "Save & parse" }).click();
      await expect(page.getByText(/Segments \(/)).toBeVisible();

      await page.getByLabel("Accent").first().selectOption("british");
      const card = page.locator("ul").first().locator("li button").first();
      await card.click();
      await expect(card).toHaveAttribute("aria-pressed", "true");

      const generate = page.getByRole("button", { name: "Generate audio" });
      await expect(generate).toBeEnabled();
      await generate.click();
      await expect(page.getByRole("button", { name: "Play" })).toBeVisible({
        timeout: 180_000,
      });
      return page
        .locator("audio")
        .evaluate((el: HTMLAudioElement) => el.duration);
    };

    const once = await durationFor("1");
    const twice = await durationFor("2");
    // Two hearings plus a one-second gap.
    expect(twice).toBeGreaterThan(once * 1.8);
  });
});
