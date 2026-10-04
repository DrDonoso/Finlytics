import { expect, test as base, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

/** What can go wrong without the page showing it: an exception a boundary
 *  swallowed, a chunk that failed to load, or a request the demo does not serve
 *  (its catch-all answers 501 and logs an error). Collected for every test and
 *  asserted empty once the test body has finished. */
const test = base.extend<{ problems: string[] }>({
  problems: [
    async ({ page }, provide) => {
      const problems: string[] = []
      page.on('pageerror', error => problems.push(`uncaught: ${error.message}`))
      page.on('console', message => {
        if (message.type() === 'error') problems.push(`console: ${message.text()}`)
      })
      page.on('response', response => {
        if (response.status() >= 400) problems.push(`HTTP ${response.status()} ${response.url()}`)
      })
      await provide(problems)
      expect(problems).toEqual([])
    },
    { auto: true },
  ],
})

/** A screen that failed, or is showing only part of what it should. */
const DEGRADED = [
  '.state-box.error',
  '.state-box[role="alert"]',
  '.dashboard-kpi-hero__notice',
  '.dashboard-kpi-breakdown__missing',
  '.inv-partial-banner',
  '.inv-snapshot-partial',
].join(', ')

/** Every route DemoRoutes exposes (App.tsx), and whether it shows amounts. */
const ROUTES = [
  { path: '/', money: true },
  { path: '/finances', money: true },
  { path: '/transactions', money: true },
  { path: '/analytics', money: true },
  { path: '/investments', money: true },
  { path: '/investments/indexa-capital', money: true },
  { path: '/investments/fidelity-espp', money: true },
  { path: '/mortgage', money: true },
  { path: '/settings/appearance', money: false },
  { path: '/settings/about', money: false },
]

/** The demo keeps its session in memory, so every page load starts signed out
 *  and the login form renders in place of the requested route. */
async function signIn(page: Page) {
  await page.locator('#auth-username').fill('demo')
  await page.locator('#auth-password').fill('demo')
  await page.getByRole('button', { name: 'Log in', exact: true }).click()
  await expect(page.locator('.app-shell')).toBeVisible()
}

async function expectAccessible(page: Page) {
  const { violations } = await new AxeBuilder({ page }).analyze()
  expect(violations.map(({ id, impact, nodes }) => ({
    id,
    impact,
    targets: nodes.map(node => node.target),
  }))).toEqual([])
}

for (const { path, money } of ROUTES) {
  test(`${path} renders its data`, async ({ page }) => {
    await page.goto(path)
    await signIn(page)

    await expect(page.locator('h1')).toHaveCount(1)
    await expect(page.locator('.icon-spin')).toHaveCount(0)
    await expect(page.getByText('Loading…', { exact: true })).toHaveCount(0)
    // An unknown path would have been redirected to the dashboard by now.
    await expect(page).toHaveURL(url => url.pathname === path)
    await expect(page.locator(DEGRADED)).toHaveCount(0)
    if (money) {
      await expect(page.locator('.private').filter({ hasText: '€', visible: true }).first()).toBeVisible()
    }
    await expectAccessible(page)
  })
}

test('the assistant answers from the demo data', async ({ page }) => {
  await page.goto('/')
  await signIn(page)

  await page.getByRole('button', { name: 'Open the assistant' }).click()
  const panel = page.getByRole('dialog', { name: 'Talk to your finances' })
  await panel.getByRole('button', { name: 'How much did I spend last month?' }).click()

  const stop = panel.getByRole('button', { name: 'Stop' })
  await expect(stop).toBeVisible()
  await expect(stop).toBeHidden({ timeout: 30_000 })
  await expect(panel.locator('.assistant-msg--assistant').last()).toContainText('€')
  await expect(panel.locator('.assistant-error')).toHaveCount(0)
  await expectAccessible(page)
})

for (const width of [1280, 390]) {
  test(`the prepayment dialog is accessible and dismisses safely at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 850 })
    await page.goto('/mortgage')
    await signIn(page)
    const opener = page.getByRole('button', { name: 'Simulate prepayment', exact: true })
    await opener.click()
    const dialog = page.getByRole('dialog', { name: 'Prepayment simulator' })
    await expect(dialog.locator('.modal')).toBeInViewport({ ratio: 1 })
    await opener.evaluate(element => element.focus())
    await expect(opener).not.toBeFocused()
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true)

    if (width <= 600) {
      const bottom = await dialog.locator('.modal').evaluate(element => element.getBoundingClientRect().bottom)
      expect(bottom).toBeCloseTo(850, 0)
    }
    await dialog.getByLabel('Amount to prepay', { exact: true }).fill('5.000,00')
    await dialog.getByRole('button', { name: 'Simulate', exact: true }).click()
    await expect(dialog.getByText('Interest saved', { exact: true })).toBeVisible()
    await expectAccessible(page)

    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(opener).toBeFocused()
    await opener.click()
    const bounds = await dialog.getByLabel('Amount to prepay', { exact: true }).boundingBox()
    if (!bounds) throw new Error('The prepayment amount input has no layout box')
    await page.mouse.move(bounds.x + 5, bounds.y + bounds.height / 2)
    await page.mouse.down()
    await page.mouse.move(1, 1)
    await page.mouse.up()
    await expect(dialog).toBeVisible()
    await page.mouse.click(1, 1)
    await expect(dialog).toHaveCount(0)
    await expect(opener).toBeFocused()
  })
}
