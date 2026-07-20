## 2026-07-17T13:04:32Z: Notifications + Telegram Feature Session Concluded

**Status:** All deliverables merged into decisions.md and squad log. Test results: 1239 passed, 2 skipped. Docker E2E: PASS. Orchestration logs written.

**Key outcome:** Hybrid notifications model + Telegram channel with Fernet encryption. Backend-owned state. No Critical findings.

## Learnings

### 2026-07-20T09:02:18+02:00: Mobile KPI grid + tx-totals fixes

**KPI grid (Finanzas `header-kpis`):**
The compact KPI strip uses `display: flex; flex-wrap: wrap` with `justify-content: flex-start`. On ≤600px, items have varying content widths (currency strings differ in length), causing uneven row packing — some rows have 3 items, some 2, sometimes a lone orphan. Root fix: switch to `display: grid; grid-template-columns: repeat(2, 1fr)` inside the `@media (max-width: 600px)` block. With 6 KPI items this always yields a clean 3×2 grid. Added `align-items: start` so label/value/delta lines always start at the cell top. Increased row gap to `14px` for more vertical breathing. Also hid `.header-kpi-divider` on mobile (a vertical line between the constant-net KPI and the filtered KPIs that has no meaning in a 2-col grid and would occupy a stray cell).

**tx-totals (StatementsPage):**
`.month-header { align-items: flex-start }` is set at the base level. At ≤600px the existing rule adds `flex-direction: column` — but because `align-items` stays `flex-start`, flex children DON'T stretch horizontally; they shrink to their intrinsic content width. The `.tx-totals` grid (already `1fr 1fr`) only spans its content, leaving dead whitespace to the right. Minimal fix: add `width: 100%` to `.month-header > .tx-totals` inside the `@media (max-width: 600px)` block. This forces the grid to fill the parent regardless of flex alignment, without touching any other component.

