/** Demo-mode configuration.
 *
 * Activated at BUILD time with `VITE_DEMO=1` (see `npm run build:demo`).
 * Everything behind `IS_DEMO` is tree-shaken out of a normal production build,
 * so MSW and the synthetic dataset never ship to real users.
 *
 * The demo is deliberately read-mostly: only transaction edits are accepted,
 * and they live in browser memory until the page is reloaded. Nothing is
 * persisted, so every visitor always starts from the same clean scenario.
 */

export const IS_DEMO: boolean = import.meta.env.VITE_DEMO === '1'

/** Username reported by the mocked auth endpoints. */
export const DEMO_USERNAME = 'demo'

/** Password accepted by the mocked login. Shown on the login screen — this is a
 *  public demo with synthetic data, so the credentials are not a secret. */
export const DEMO_PASSWORD = 'demo'

/** Seed for the synthetic dataset. Fixed on purpose: a deterministic scenario is
 *  reproducible and testable, which per-visitor randomisation is not. */
export const DEMO_SEED = 20260729

/** Months of history generated, counting back from the current month. */
export const DEMO_MONTHS = 18

/** Connector views the demo has data for. Anything else (Fidelity ESPP) would
 *  render a view whose endpoints are unhandled, so it is treated as unavailable
 *  — see `investments/PluginViewWrapper.tsx`. */
export const DEMO_PLUGIN_IDS: readonly string[] = ['indexa-capital']
