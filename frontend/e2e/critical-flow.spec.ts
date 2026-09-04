import { expect, test } from "@playwright/test";

test("GM and player complete the local multiplayer slice", async ({
  page,
  browser,
}) => {
  test.setTimeout(120_000);
  const campaign = `E2E ${Date.now()}`;
  await page.goto("/");
  await page.getByRole("link", { name: "Создать комнату" }).click();
  await expect(
    page.getByRole("heading", { name: "Создать комнату" }),
  ).toBeVisible();
  await page.getByLabel("Название кампании").fill(campaign);
  await page.getByRole("button", { name: "Создать и открыть панель" }).click();
  await expect(page.getByRole("heading", { name: campaign })).toBeVisible();
  await page.getByRole("button", { name: "Новый QR" }).click();
  const shortCode = await page.locator(".pairing strong").innerText();

  const playerContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  const player = await playerContext.newPage();
  await player.goto("/");
  await player.getByLabel("Короткий код подключения").fill(shortCode);
  await player.getByRole("button", { name: "Подключиться как игрок" }).click();
  await player.getByLabel("Имя за столом").fill("Mira");
  await player.getByRole("button", { name: "Войти в комнату" }).click();

  await player
    .getByRole("button", { name: "Личный кабинет", exact: true })
    .click();
  await expect(
    player.getByRole("button", { name: "Бой", exact: true }),
  ).toHaveCount(0);
  await expect
    .poll(() =>
      player.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
  await player.getByLabel("Имя нового персонажа").fill("Aria");
  for (let step = 0; step < 3; step += 1) {
    await player.getByRole("button", { name: "Далее" }).click();
  }
  await player.getByRole("button", { name: "Подтвердить расу" }).click();
  for (let step = 0; step < 2; step += 1) {
    await player.getByRole("button", { name: "Далее" }).click();
  }
  await player
    .getByRole("button", { name: "К карточкам способностей" })
    .click();
  for (let round = 0; round < 4; round += 1) {
    await player.locator(".ability-card").first().click();
  }
  await expect(player.getByText("Сила", { exact: true })).toBeVisible();
  await player.screenshot({
    path: "test-results/corrective-visual/player-preview-390.png",
    fullPage: true,
  });
  await player.setViewportSize({ width: 360, height: 800 });
  await expect
    .poll(() =>
      player.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
  await player.screenshot({
    path: "test-results/corrective-visual/player-preview-360.png",
    fullPage: true,
  });
  await player.setViewportSize({ width: 390, height: 844 });
  await player.getByRole("button", { name: "Подтвердить персонажа" }).click();
  await expect(player.getByText("Aria", { exact: true })).toBeVisible();
  await player
    .getByRole("dialog", { name: "Личный кабинет" })
    .getByRole("button", { name: "Закрыть" })
    .click();

  await expect(page.getByText("Mira")).toBeVisible();
  await page.getByRole("button", { name: "Новая сессия" }).click();
  await page.getByRole("button", { name: "Открыть лобби" }).click();
  await page.getByRole("button", { name: "Начать игру" }).click();
  await expect(player.getByText("ACTIVE", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Бой", exact: true }).click();
  await page.getByPlaceholder("Название нового энкаунтера").fill("Засада");
  await page.getByRole("button", { name: "Подготовить энкаунтер" }).click();
  await expect(page.getByRole("heading", { name: "Раунд 0" })).toBeVisible();
  await page
    .getByRole("button", { name: "Добавить выбранных персонажей" })
    .click();
  await expect(
    page.locator(".initiative-list").getByText("Aria", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/corrective-visual/gm-combat-form.png",
    fullPage: true,
  });
  await page.getByLabel("Имя монстра").fill("Гоблин");
  await page.getByLabel("HP монстра").fill("10");
  await page.getByLabel("Количество монстров").fill("2");
  await page.getByLabel("Раса(ы)").fill("Гоблиноид");
  await page
    .locator(".combat-monster-form")
    .getByRole("button", { name: "Добавить", exact: true })
    .click();
  await expect(page.getByText("2 участника")).toBeVisible();
  await page.screenshot({
    path: "test-results/corrective-visual/gm-combat-list.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Начать бой" }).click();

  await page.locator(".initiative").filter({ hasText: "Гоблин" }).click();
  await page.getByLabel("Величина эффекта").fill("6");
  await page.getByRole("button", { name: "Нанести урон" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Закрыть" })
    .click();
  await page.getByRole("button", { name: "Следующий ход" }).click();
  await player.getByRole("button", { name: "Кубики", exact: true }).click();
  await player.getByRole("button", { name: "С преимуществом" }).click();
  await player.locator(".die-button").filter({ hasText: "d20" }).click();
  await expect(player.getByText("Кубики катятся…")).toBeVisible();
  await expect(player.getByText("Результат")).toBeVisible({ timeout: 3000 });
  await player.getByRole("button", { name: "Закрыть" }).click();
  await page.getByRole("button", { name: "Кубики", exact: true }).click();
  await expect(page.getByText("С преимуществом").last()).toBeVisible();
  await page.getByRole("button", { name: "Бой", exact: true }).click();
  await page.getByRole("button", { name: "Завершить бой" }).click();
  await expect(
    page.getByText("БОЙ · COMPLETED", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Персонажи", exact: true }).click();
  await page.getByRole("button", { name: /Aria/ }).click();
  await expect(page.getByText("Сила", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "test-results/corrective-visual/gm-character-card.png",
    fullPage: true,
  });

  await player.getByRole("button", { name: "Персонаж", exact: true }).click();
  await player.getByPlaceholder("Новый предмет").fill("Rope");
  await player.getByRole("button", { name: "Добавить" }).click();
  await expect(player.getByText("Rope")).toBeVisible();
  await player.reload();
  await player.getByRole("button", { name: "Персонаж", exact: true }).click();
  await expect(player.getByRole("heading", { name: "Aria" })).toBeVisible();
  await player.getByRole("button", { name: "Удалить 1" }).click();
  await expect(player.getByText("Инвентарь пуст.")).toBeVisible();

  await page.getByRole("button", { name: "Лобби", exact: true }).click();
  await page.getByRole("button", { name: "Завершить сессию" }).click();
  await expect(page.getByText("Нет активной")).toBeVisible();
  await playerContext.close();
});
