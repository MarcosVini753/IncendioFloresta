import { describe, expect, it } from 'vitest'
import { ACRE_MUNICIPALITY_SEATS } from './acreMunicipalities'

describe('sede dos municípios do Acre', () => {
  it('inclui os 22 municípios sem duplicação de código IBGE', () => {
    expect(ACRE_MUNICIPALITY_SEATS).toHaveLength(22)
    expect(new Set(ACRE_MUNICIPALITY_SEATS.map((item) => item.id)).size).toBe(22)
    expect(ACRE_MUNICIPALITY_SEATS.every((item) => item.id.startsWith('12'))).toBe(true)
  })
  it('usa coordenadas geográficas válidas na região do Acre', () => {
    expect(ACRE_MUNICIPALITY_SEATS.every((item) =>
      item.latitude >= -12 && item.latitude <= -7 &&
      item.longitude >= -74 && item.longitude <= -66,
    )).toBe(true)
  })
})
