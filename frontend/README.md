# Finlytics — Frontend

Dashboard de gastos personales. Stack: **Vite + React + TypeScript + Recharts**.

## Desarrollo

```bash
npm install
npm run dev        # http://localhost:5173
```

Requiere que el backend (Shuri/FastAPI) esté corriendo en `http://localhost:8000`.

### Modo mock (sin backend)

```bash
VITE_USE_MOCK=1 npm run dev
```

Con `VITE_USE_MOCK=1` el dashboard carga datos de demostración (BBVA + Indexa Capital, mayo–junio 2026) sin llamar a la API.

## Build de producción

```bash
npm run build      # salida: frontend/dist/
npm run preview    # sirve el build localmente en :4173
```

FastAPI sirve `frontend/dist/` como SPA estática en producción (`/` → `index.html`, `/api/*` → API).

## Estructura

```
src/
├── api/
│   ├── types.ts        # Interfaces TypeScript para todos los contratos de API
│   ├── client.ts       # Fetch client tipado; fallback a mock en error o VITE_USE_MOCK=1
│   └── mock.ts         # Datos realistas (BBVA + Indexa, mayo–junio 2026)
├── components/
│   ├── GlobalFilterBar.tsx    # Filtro global: rango de fechas + cuenta
│   ├── KpiCards.tsx           # Tarjetas KPI: gasto, ingreso, neto, top categoría
│   ├── SpendingByCategory.tsx # Donut chart por categoría (Recharts)
│   ├── SpendingOverTime.tsx   # Bar chart mensual gasto vs ingreso (Recharts)
│   ├── SpendingByAccount.tsx  # Bar chart por cuenta (Recharts)
│   └── TransactionsTable.tsx  # Tabla paginada con filtros
└── pages/
    └── Dashboard.tsx   # Página principal; orquesta todos los componentes
```

## Variables de entorno

| Variable | Valores | Descripción |
|---|---|---|
| `VITE_USE_MOCK` | `1` / (vacío) | Fuerza datos mock sin llamar al backend |
