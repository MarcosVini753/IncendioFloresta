import type { FeatureCollection, Point } from 'geojson'

export interface InpeHotspotProperties {
  data_hora_gmt?: string | null
  satelite?: string | null
  pais?: string | null
  estado?: string | null
  municipio?: string | null
  bioma?: string | null
  dias_sem_chuva?: number | null
  precipitacao?: number | null
  risco_fogo?: number | null
  frp?: number | null
  fonte: string
}

export interface InpeHotspotMetadata {
  fonte: string
  fonte_url?: string
  arquivo_origem: string
  estado: string
  data_referencia?: string
  gerado_em_utc: string
  quantidade_focos: number
}

export interface InpeHotspotCollection
  extends FeatureCollection<Point, InpeHotspotProperties> {
  metadata: InpeHotspotMetadata
}
