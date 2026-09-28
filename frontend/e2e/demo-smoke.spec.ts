import { expect, test as base, type Page } from '@playwright/test'

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
})
