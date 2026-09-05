import { expect, test, type Page } from "@playwright/test";

test.use({ locale: "en-US" });

const EDITOR = '[role="textbox"][contenteditable]';

/** Select a whole line, the way a user drags across it. */
async function selectLine(page: Page, index: number) {
  await page.evaluate((i) => {
    const editor = document.querySelector<HTMLElement>(
      '[role="textbox"][contenteditable]',
    )!;
    editor.focus();
    const line = editor.querySelectorAll("div")[i];
    const range = document.createRange();
    range.selectNodeContents(line);
    const selection = window.getSelection()!;
    selection.removeAllRanges();
    selection.addRange(range);
  }, index);
}

async function openDialogue(page: Page, title: string) {
  await page.goto("/create");
  await page.getByRole("button", { name: "Dialogue" }).click();
  await page.getByLabel("Project title").fill(title);
  await expect(page.locator(EDITOR)).toBeVisible();
}

test.describe("styling assigns speakers", () => {
  test("word-processor shortcuts apply the marks", async ({ page }) => {
    await openDialogue(page, "Shortcuts");

    // The same chords Word uses. Ctrl works alongside Cmd so the app behaves
    // the same on Windows.
    await selectLine(page, 0);
    await page.keyboard.press("ControlOrMeta+b");
    await expect(page.locator(`${EDITOR} b, ${EDITOR} strong`)).toHaveCount(2);

    await selectLine(page, 2);
    await page.keyboard.press("ControlOrMeta+i");
    await expect(page.locator(`${EDITOR} i, ${EDITOR} em`)).toHaveCount(1);

    await selectLine(page, 2);
    await page.keyboard.press("ControlOrMeta+u");
    await expect(page.locator(`${EDITOR} u`)).toHaveCount(1);
  });

  test("the toolbar applies the same marks", async ({ page }) => {
    await openDialogue(page, "Toolbar");

    await selectLine(page, 2);
    await page.getByRole("button", { name: "Underline", exact: true }).click();
    await expect(page.locator(`${EDITOR} u`)).toHaveCount(1);
  });

  test("each style becomes its own numbered voice", async ({ page }) => {
    await openDialogue(page, "Styled speakers");

    // Line 1 plain, line 2 italic, line 3 underline -> three speakers.
    await selectLine(page, 1);
    await page.keyboard.press("ControlOrMeta+b"); // clear the sample's bold
    await selectLine(page, 1);
    await page.keyboard.press("ControlOrMeta+i");
    await selectLine(page, 2);
    await page.keyboard.press("ControlOrMeta+u");

    await page.getByRole("button", { name: "Save & parse" }).click();
    await expect(page.getByText(/Segments \(/)).toBeVisible();

    const headings = page.locator("h3").filter({ hasText: /^Voice \d/ });
    await expect(headings).toHaveCount(3);
    await expect(headings.nth(0)).toContainText("Plain");
    await expect(headings.nth(1)).toContainText("Italic");
    await expect(headings.nth(2)).toContainText("Underline");
  });

  test("a styled dialogue hides the speaker-count control", async ({ page }) => {
    await openDialogue(page, "No count");
    await page.getByRole("button", { name: "Save & parse" }).click();
    await expect(page.getByText(/Segments \(/)).toBeVisible();

    // The formatting used decides how many speakers there are, so a count
    // control would only contradict it.
    await expect(page.getByLabel("Number of speakers")).toHaveCount(0);
  });

  test("restyling drops the slot that is no longer used", async ({ page }) => {
    await openDialogue(page, "Restyle");
    await page.getByRole("button", { name: "Save & parse" }).click();
    await expect(page.locator("h3").filter({ hasText: /^Voice \d/ })).toHaveCount(2);

    // Make every line plain: one speaker should remain.
    await selectLine(page, 1);
    await page.keyboard.press("ControlOrMeta+b");
    await page.getByRole("button", { name: "Save & parse" }).click();
    await expect(page.locator("h3").filter({ hasText: /^Voice \d/ })).toHaveCount(1);
  });

  test("pasted text arrives unstyled", async ({ page }) => {
    await openDialogue(page, "Paste");
    // Styling carried in from another document would silently reassign
    // speakers, so paste is plain-text only.
    await page.locator(EDITOR).click();
    await page.evaluate(() => {
      const editor = document.querySelector<HTMLElement>(
        '[role="textbox"][contenteditable]',
      )!;
      const data = new DataTransfer();
      data.setData("text/plain", "Pasted plain line.");
      editor.dispatchEvent(
        new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }),
      );
    });
    await expect(page.locator(EDITOR)).toContainText("Pasted plain line.");
  });
});
