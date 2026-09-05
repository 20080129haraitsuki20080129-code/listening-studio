import { expect, test } from "@playwright/test";

test.use({ locale: "en-US" });

test.describe("speed levels", () => {
  test("seven levels, each labelled by a pace", async ({ page }) => {
    await page.goto("/create");
    const slider = page.getByLabel("Speed");
    await expect(slider).toHaveAttribute("min", "1");
    await expect(slider).toHaveAttribute("max", "7");

    // A bare multiplier says nothing about pace. The exact figures come from
    // measurement and are expected to change, so assert the shape, not the
    // numbers.
    for (const level of ["1", "4", "7"]) {
      await slider.fill(level);
      await expect(
        page.getByText(new RegExp(`Level ${level} · about \\d+ words/min`)),
      ).toBeVisible();
      await expect(
        page.getByText(/\d+-\d+ depending on the voice/),
      ).toBeVisible();
    }
  });

  test("the scale is anchored to recognisable material", async ({ page }) => {
    await page.goto("/create");
    const slider = page.getByLabel("Speed");

    // The middle of the scale is exam pace and the top is a heated argument;
    // that is what makes the scale mean something.
    await slider.fill("4");
    await expect(page.getByText("university entrance exam")).toBeVisible();

    await slider.fill("7");
    await expect(page.getByText("heated native argument")).toBeVisible();
  });

  test("pace rises with every level", async ({ page }) => {
    await page.goto("/create");
    const slider = page.getByLabel("Speed");
    const paces: number[] = [];
    for (let level = 1; level <= 7; level++) {
      await slider.fill(String(level));
      const text = await page
        .getByText(/Level \d · about \d+ words\/min/)
        .innerText();
      paces.push(Number(text.match(/about (\d+)/)![1]));
    }
    expect(paces).toEqual([...paces].sort((a, b) => a - b));
    expect(new Set(paces).size).toBe(7);
  });

  test("the chosen level survives a reload", async ({ page }) => {
    await page.goto("/create");
    await page.getByLabel("Project title").fill("Pace");
    await page.getByLabel("English script").fill("One sentence here.");
    await page.getByLabel("Speed").fill("2");
    await page.getByRole("button", { name: "Save & parse" }).click();
    await expect(page.getByText(/Segments \(/)).toBeVisible();

    await page.reload();
    await expect(page.getByLabel("Speed")).toHaveValue("2");
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

test.describe("measured pace", () => {
  test("reported only after a render, and taken from the audio", async ({
    page,
  }) => {
    await page.goto("/create");
    await page.getByLabel("Project title").fill("Measured");
    await page
      .getByLabel("English script")
      .fill(
        "Climate change is altering migration patterns across the world. " +
          "Researchers say the shift is accelerating in every region they studied.",
      );
    await page.getByRole("button", { name: "Save & parse" }).click();
    await expect(page.getByText(/Segments \(/)).toBeVisible();

    // Nothing has been spoken yet, so there is no rate to report.
    await expect(page.getByText(/Measured:/)).toHaveCount(0);

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

    const measured = page.getByText(/Measured: \d+ words\/min/);
    await expect(measured).toBeVisible();

    // The advertised band is an estimate; this is the fact. It should at
    // least be a plausible speaking rate.
    const wpm = Number((await measured.innerText()).match(/(\d+)/)![1]);
    expect(wpm).toBeGreaterThan(60);
    expect(wpm).toBeLessThan(400);
  });
});
