# Decisions Archive

Archivals from main decisions.md (entries older than 7 days).

---

## Vision: Inicio/Finanzas Split + InvestmentSnapshotCard + ImportSourcePicker (2026-07-15)

**Fecha:** 2026-07-15T16:20:19+02:00  
**Autor:** Vision (Frontend Engineer)  
**Solicitado por:** DrDonoso (David)  
**Estado:** SHIPPED — build limpio, 0 errores TS

### Contexto

Batch de 5 items de feedback del owner implementa la propuesta MOVE+REPLACE de Wanda (`.squad/decisions.md` § "PROPOSAL: Recomendación: Inicio vs Finanzas") — esta decisión estaba marcada como pendiente.

### Decisiones implementadas

**1. Connectors — Eliminar botón "Resumen" de Fidelity ESPP cuando conectado**  
Card connected muestra solo: badge ✓ + botón Desconectar. Archivo: `ConnectorsPage.tsx` — `renderFidelityEsppCard`.

**2. Settings groups collapsed por defecto**  
Los 4 grupos colapsables (Datos/Reglas/Sistema/Aplicación) usan `useState(false)`. Archivo: `Layout.tsx` líneas ~57-60.

**3. Split Inicio vs Finanzas — MOVE + REPLACE** (Principio: cada widget tiene UN único hogar. Sin duplicación.)

| Componente | Antes | Ahora |
|---|---|---|
| `GlobalFilterBar` | ✅ | ❌ |
| `SpendingByCategory` | ✅ | ❌ |
| `TopMerchants` | ✅ | ❌ |
| `SpendingHeatmap` | ✅ | ❌ |
| `CategoryMovers` | ✅ | ❌ |
| `KpiCards` | ✅ Filtrable | ✅ Mes actual fijo |
| `InvestmentSnapshotCard` | ❌ | ✅ Nuevo |
| Botón Importar | File picker | `ImportSourcePicker` |

**Nota:** `defaultRange()` devuelve mes anterior; Dashboard usa `currentMonthRange()` inline para mes en curso.

**Finanzas:** Hereda GlobalFilterBar, KpiCards (con previousOverview), SpendingByCategory, TopMerchants; AÑADE SpendingHeatmap, CategoryMovers, ImportLauncher + ImportModal.

**4. Botón Importar en Finanzas**  
`ImportLauncher` + `ImportModal` + `refreshKey` + `toast` en `FinancesOverviewPage.tsx`. Tras importar, `refreshKey` dispara re-fetch de todos los datos.

**5. Inicio: Importar → ImportSourcePicker (data-driven)**  
Nuevo componente `ImportSourcePicker.tsx`:
- Siempre lista "Extractos bancarios" (file picker).
- Fetches `GET /api/investments/plugins` y filtra `import_route !== null`.
- Fidelity ESPP → `import_route: '/investments/fidelity-espp'` (Shuri backend).
- Extensible: futuros plugins aparecen automáticamente.

Tipo actualizado: `InvestmentPlugin.import_route: string | null` en `api/types.ts`.

**6. Nuevo componente: InvestmentSnapshotCard**  
`frontend/src/components/InvestmentSnapshotCard.tsx`:
- Fetches `GET /api/investments/combined-overview`.
- Loading → spinner. Error → error box. Vacío → mensaje + link "Ver inversiones →".
- Populated → total_value_eur grande + desglose por provider (icon + name + value_eur).
- `fmtEur(null)` → "—".
- Header siempre muestra link a `/investments`. CSS: clases `inv-snapshot-*` en `index.css`.

### Archivos modificados/creados

| Archivo | Cambio |
|---|---|
| `frontend/src/api/types.ts` | `InvestmentPlugin.import_route: string \| null` |
| `frontend/src/api/mock.ts` | `import_route` en todos plugins; fidelity-espp entry |
| `frontend/src/i18n/index.ts` | 7 nuevas claves (invSnapshot*, importPicker*) |
| `frontend/src/i18n/es.ts` | 7 traducciones ES |
| `frontend/src/i18n/en.ts` | 7 traducciones EN |
| `frontend/src/components/Layout.tsx` | sg* collapsed por defecto |
| `frontend/src/pages/ConnectorsPage.tsx` | Eliminado Link "Resumen" en Fidelity connected |
| `frontend/src/pages/Dashboard.tsx` | Reescrito como hub cross-domain |
| `frontend/src/pages/FinancesOverviewPage.tsx` | Heatmap + Movers + Import añadidos |
| `frontend/src/index.css` | CSS para inv-snapshot-* e import-picker-* |
| `frontend/src/components/InvestmentSnapshotCard.tsx` | **Nuevo** |
| `frontend/src/components/ImportSourcePicker.tsx` | **Nuevo** |

**Build:** `tsc --noEmit && vite build` → 0 TypeScript errors, built in 6.48s ✓


---

# DESIGN SPEC + PROPOSAL: Reestructuración de navegación y páginas overview

**Autora:** Wanda (UX/UI Designer)  
**Fecha:** 2026-07-15  
**Implementador:** Vision (Frontend Engineer)  
**Estado:** Spec lista para implementación


---

# Decision: Combined Investments Overview Endpoint

**Autora:** Shuri (Backend Engineer)  
**Fecha:** 2026-07-15  
**Estado:** Implementado ✅


---

# IMPL MEMO: Nav restructure + Finanzas overview + Investments combined

**Autor:** Vision (Frontend Engineer)
**Fecha:** 2026-07-15T14:10:06+02:00
**Spec origen:** `.squad/decisions/inbox/wanda-nav-restructure-overviews.md`
**Estado:** Implementado · build limpio · pendiente endpoint Shuri


---

**Coordinators:** Shuri (Backend), Vision (Frontend), Rocket (DevOps)  
**Status:** COMPLETE & VERIFIED IN DOCKER  

**Summary:**
- ✅ Plugin discovery: Fidelity ESPP registered in _PLUGIN_REGISTRY + dynamic status in list_plugins (1070 → 1088 tests)
- ✅ Price source: Yahoo Chart API primary (browser User-Agent required; query1→query2 fallback) with lazy backfill
- ✅ Upload UI: Styled file picker + SP/DO tooltips (i18n ES/EN) 
- ✅ Verified in Docker: MSFT €337.04, EUR/USD 0.87558, evolution chart functional
- 🔄 Repo code: Uncommitted; owner testing/iterating
# ADR: Yahoo Chart API como fuente de precio primaria para Fidelity ESPP

**Fecha:** 2026-07-15  
**Autor:** Shuri (Backend Engineer)  
**Estado:** Implementado  
**Contexto:** Bugfix — precio MSFT nulo en Docker, gráfico de evolución sin datos


---

# Refinamiento Arquitectónico: Fidelity ESPP — CSV-First + Input Adapters

**Autor:** Fury (Lead/Architect)  
**Fecha:** 2026-07-15T08:51:14+02:00  
**Status:** PROPUESTA — pendiente aprobación del owner  
**Contexto:** El owner respondió a las preguntas de scoping de la arquitectura inicial. Nuevas decisiones: accumulate-only, prev-close pricing, sin descuento ESPP, generic-ready, y MUY IMPORTANTE: puede entregar un CSV de current shares en lugar del PDF.


---

# ESPP PDF Storage & Privacy Review — Fidelity Statement

**Fecha:** 2026-07-15T08:51:14+02:00  
**Autor:** Romanoff (Security/Privacy Engineer)  
**Estado:** RECOMENDACIÓN — pendiente de decisión del owner


---

# Fidelity "View open lots" CSV — Probe Findings

**Autor:** Banner (Data/AI Engineer)  
**Fecha:** 2026-07-15T09:24:54+02:00  
**Status:** FINDINGS — para Fury (arquitectura), Shuri (schema), Romanoff (PII review)  
**Contexto:** El owner puede exportar un CSV de "View open lots" desde Fidelity en lugar del PDF. Este documento recoge los hallazgos del probe real del fichero.


---

## 🎨 PROPOSAL: Recomendación: Inicio vs Finanzas — Diferenciación de Pantallas

**Autora:** Wanda (UX/UI Designer)  
**Fecha:** 2026-07-15  
**Estado:** Propuesta — pendiente decisión del owner

### 1. ¿Para qué sirve cada pantalla?

| Pantalla | Propósito | Analogía |
|----------|-----------|----------|
| **Inicio** (`/`) | **Cuadro de mando personal** — snapshot cross-domain (gastos + inversiones) del estado financiero actual. Responde a: *"¿cómo estoy?"* en 3 segundos. | La pantalla de bloqueo del iPhone: lo justo para saber si algo requiere atención. |
| **Finanzas** (`/finances`) | **Centro de operaciones de gasto** — análisis enfocado de ingresos/gastos con filtros completos. Responde a: *"¿en qué me he gastado el dinero este mes?"* con capacidad de drill-down. | La app del banco abierta en la sección de movimientos. |

**Principio clave:** Inicio NO es un dashboard de finanzas reducido. Inicio es el *hub* que abarca TODO (gastos + inversiones). Finanzas es la herramienta de análisis de cash-flow.

### 2. Recomendación: **MOVER + REEMPLAZAR** (ni duplicar, ni simplemente quitar)

**Dirección concreta:**

1. **MOVER a Finanzas:** SpendingByCategory, TopMerchants, CategoryMovers, SpendingHeatmap, y GlobalFilterBar. Finanzas se convierte en el dashboard de análisis de gasto *completo*.

2. **REEMPLAZAR en Inicio:** Sustituir los widgets movidos por contenido cross-domain:
   - KPIs simplificados del mes actual (sin filtros) — gasto del mes, ingreso del mes, neto
   - Nuevo widget de patrimonio/inversiones (valor total de cartera + variación)
   - Accesos rápidos a secciones

3. **NO DUPLICAR:** Cada widget debe tener UN hogar.

**Justificación:** Con la app creciendo a gastos + inversiones, Inicio necesita ser el punto de encuentro de ambos mundos. Hacerlo cross-domain le da un propósito único e insustituible.

### 3. Propuesta de layout — Inicio ideal

```
KPIs del mes (julio 2026) — Gastos, Ingresos, Neto, Ahorro
Patrimonio inversiones — Valor total, ganancia/pérdida, desglose por proveedor
Accesos rápidos — Finanzas, Inversiones, Tendencias, Ajustes
```

### 4. Finanzas ideal propuesto

Con los widgets movidos:
- GlobalFilterBar — filtros
- KpiCards — con filtros aplicados
- SpendingByCategory (donut) + TopMerchants (side by side)
- SpendingHeatmap — full width
- CategoryMovers — full width

### 5. Necesidades de datos / endpoints nuevos

| Necesidad | Endpoint | Estado |
|-----------|----------|--------|
| KPIs mes actual en Inicio | `getOverview({ from, to })` | ✅ Ya existe |
| Patrimonio inversiones en Inicio | `GET /api/investments/combined-overview` | ✅ Ya existe |
| CategoryMovers en Finanzas | `getByCategory()` | ✅ Ya existe |
| SpendingHeatmap en Finanzas | `getHeatmap()` | ✅ Ya existe |

**🎉 No se necesita NINGÚN endpoint nuevo.** Solo:
1. Nuevo componente React `InvestmentSnapshotCard` (compact) para Inicio
2. Reorganizar qué componentes renderiza cada página

### 6. Riesgos y consideraciones

- **Inicio queda "ligero":** Intencionado. Mobile-first = menos scroll, más foco.
- **Pérdida de interactividad en Inicio:** Sin filtros, Inicio es solo lectura. Esto es una feature (reduce carga cognitiva). Para interactuar → Finanzas.
- **Accesos rápidos pueden parecer innecesarios con el sidebar:** En desktop sí. En mobile, donde el sidebar está colapsado, son muy útiles como primer punto de contacto.

### 7. Resumen ejecutivo

> **Inicio = Vistazo rápido cross-domain (gastos del mes + inversiones + shortcuts)**
> **Finanzas = Análisis completo de cash-flow con filtros**
> **Dirección: MOVER widgets de análisis a Finanzas, REEMPLAZAR en Inicio con contenido cross-domain. No duplicar.**
> **Backend: 0 endpoints nuevos necesarios.**


