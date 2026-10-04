import type { Dict } from '../i18n'

export function assetClassLabel(assetClass: string, t: Dict): string {
  switch (assetClass) {
    case 'equity': return t.invAssetEquity
    case 'fixed_income': return t.invAssetFixed_income
    case 'cash': return t.invAssetCash
    case 'espp_stock': return t.invAssetEspp_stock
    case 'mixed': return t.invAssetMixed
    case 'other': return t.invAssetOther
    default: return assetClass
  }
}
