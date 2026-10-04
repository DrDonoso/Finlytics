/**
 * The API sends asset classes as stable keys, and the label is chosen here so
 * the Spanish UI does not print the backend's English fallback.
 */
import { describe, expect, it } from 'vitest'

import en from '../i18n/en'
import es from '../i18n/es'
import { assetClassLabel } from './assetClass'

describe('assetClassLabel', () => {
  it.each([
    ['equity', 'Renta variable', 'Equity'],
    ['fixed_income', 'Renta fija', 'Fixed income'],
    ['cash', 'Efectivo', 'Cash'],
    ['other', 'Otros', 'Other'],
    ['espp_stock', 'Acciones ESPP', 'ESPP stock'],
    ['mixed', 'Mixto', 'Mixed'],
  ])('translates %s', (assetClass, esLabel, enLabel) => {
    expect(assetClassLabel(assetClass, es)).toBe(esLabel)
    expect(assetClassLabel(assetClass, en)).toBe(enLabel)
  })

  it('passes an unknown class through unchanged', () => {
    expect(assetClassLabel('crypto', es)).toBe('crypto')
  })
})
