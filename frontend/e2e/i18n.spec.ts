import { expect, test } from "@playwright/test";

const STORAGE_KEY = "listening-studio.locale";

test.describe("language switching", () => {
  test("defaults to English and switches the whole UI to Japanese", async ({
    page,
  }) => {
    await page.goto("/create");

    await expect(page.getByRole("button", { name: "Save & parse" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Monologue" })).toBeVisible();

    await page.getByRole("button", { name: "日本語" }).click();

    await expect(page.getByRole("button", { name: "保存して解析" })).toBeVisible();
    await expect(page.getByRole("button", { name: "単読" })).toBeVisible();
    await expect(page.getByRole("button", { name: "会話" })).toBeVisible();
    await expect(page.getByText("生成時の話速")).toBeVisible();

    // Accent options come from the API but are labelled from the catalog.
    await expect(
      page.getByRole("option", { name: "イギリス英語" }).first(),
    ).toBeAttached();

    await page.getByRole("button", { name: "English" }).click();
    await expect(page.getByRole("button", { name: "Save & parse" })).toBeVisible();
  });

  test("the choice persists across a reload", async ({ page }) => {
    await page.goto("/create");
    await page.getByRole("button", { name: "日本語" }).click();
    await expect(page.getByRole("button", { name: "保存して解析" })).toBeVisible();

    await page.reload();
    await expect(page.getByRole("button", { name: "保存して解析" })).toBeVisible();

    const stored = await page.evaluate(
      (key) => window.localStorage.getItem(key),
      STORAGE_KEY,
    );
    expect(stored).toBe("ja");
  });

  test("sets the document language for screen readers", async ({ page }) => {
    await page.goto("/create");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");

    await page.getByRole("button", { name: "日本語" }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", "ja");
  });

  test("a Japanese browser starts in Japanese without a stored choice", async ({
    browser,
  }) => {
    const context = await browser.newContext({ locale: "ja-JP" });
    const page = await context.newPage();
    await page.goto("/create");

    await expect(page.getByRole("button", { name: "保存して解析" })).toBeVisible();
    await context.close();
  });

  test("the player and project list are localized too", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "日本語" }).click();
    await expect(page.getByRole("link", { name: "新規プロジェクト" })).toBeVisible();

    await page.getByRole("link", { name: "新規プロジェクト" }).click();
    await expect(page.getByText("音声を生成すると再生できます。")).toBeVisible();
  });
});

test.describe("dialogue voice slots", () => {
  test("the speaker count control applies to a marker dialogue", async ({
    page,
  }) => {
    await page.goto("/create");
    await page.getByRole("button", { name: "Dialogue" }).click();
    await page.getByLabel("Project title").fill("Slots");

    // Type [A] / [B] markers as plain text: with no styling present the
    // dialogue falls back to markers, where the count control applies.
    const editor = page.locator('[role="textbox"][contenteditable]');
    await editor.click();
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.type("[A]");
    await page.keyboard.press("Enter");
    await page.keyboard.type("Hello there.");
    await page.keyboard.press("Enter");
    await page.keyboard.type("[B]");
    await page.keyboard.press("Enter");
    await page.keyboard.type("Hi back.");

    await page.getByRole("button", { name: "Save & parse" }).click();
    await expect(page.getByText(/Segments \(/)).toBeVisible();

    const count = page.getByLabel("Number of speakers");
    await expect(count).toBeVisible();
    await count.selectOption("4");
    await expect(page.locator("h3").filter({ hasText: /^Voice \d/ })).toHaveCount(4);
    await expect(page.getByText("marked [D] in the script")).toBeVisible();

    await count.selectOption("2");
    await expect(page.locator("h3").filter({ hasText: /^Voice \d/ })).toHaveCount(2);
  });

  test("the voice list offers no engine choice", async ({ page }) => {
    await page.goto("/create");
    // Wait for the catalog before reading the filter's options.
    await expect(page.getByText(/of \d+ voices/)).toBeVisible();

    // Which engine produced a voice is not something a listener can hear, so
    // it is neither filterable nor shown.
    await expect(page.getByLabel("Provider")).toHaveCount(0);
    await expect(page.getByText("kokoro")).toHaveCount(0);

    const accents = await page
      .getByLabel("Accent")
      .first()
      .locator("option")
      .allInnerTexts();
    expect(accents).toEqual(["All accents", "American", "British"]);
  });
});

test.describe("downloads", () => {
  test("the transcript downloads as a PDF once parsed", async ({ page }) => {
    await page.goto("/create");
    await page.getByLabel("Project title").fill("Downloadable");
    await page.getByLabel("English script").fill("A downloadable sentence.");
    await page.getByRole("button", { name: "Save & parse" }).click();
    await expect(page.getByText(/Segments \(/)).toBeVisible();

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("link", { name: "Script (PDF)" }).click(),
    ]);
    expect(download.suggestedFilename()).toBe("Downloadable.pdf");
  });

  test("audio download appears only after a render", async ({ page }) => {
    await page.goto("/create");
    await page.getByLabel("Project title").fill("Audible");
    await page.getByLabel("English script").fill("An audible sentence here.");
    await page.getByRole("button", { name: "Save & parse" }).click();

    await expect(page.getByText("Generate the audio first.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Audio (MP3)" })).toHaveCount(0);

    await page.getByLabel("Accent").first().selectOption("british");
    const card = page.locator("ul").first().locator("li button").first();
    await card.click();
    await expect(card).toHaveAttribute("aria-pressed", "true");

    const generateButton = page.getByRole("button", { name: "Generate audio" });
    await expect(generateButton).toBeEnabled();
    await generateButton.click();
    await expect(page.getByRole("button", { name: "Play" })).toBeVisible({
      timeout: 180_000,
    });

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("link", { name: "Audio (MP3)" }).click(),
    ]);
    expect(download.suggestedFilename()).toBe("Audible.mp3");
  });
});
