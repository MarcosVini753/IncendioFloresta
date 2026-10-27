import type { Map as MapLibreMap } from 'maplibre-gl'

export const MUNICIPAL_SOURCE_ID = 'acre-municipality-boundaries'
export const MUNICIPAL_LINE_ID = 'acre-municipality-outline'
export const MUNICIPAL_GEOJSON_URL = '/data/reference/acre-municipalities.geojson'

// Os 22 polígonos foram compilados a partir das malhas municipais do IBGE.
// Usados exclusivamente como referência cartográfica, sem alterar os dados de risco.
// Fonte preparada para web: https://github.com/henriquemalvar/br-geojson
export function addMunicipalBoundaryLayer(
  map: MapLibreMap,
  visible: boolean,
  beforeId?: string,
) {
  map.addSource(MUNICIPAL_SOURCE_ID, {
    type: 'geojson',
    data: MUNICIPAL_GEOJSON_URL,
  })
  map.addLayer(
    {
      id: MUNICIPAL_LINE_ID,
      type: 'line',
      source: MUNICIPAL_SOURCE_ID,
      layout: { visibility: visible ? 'visible' : 'none', 'line-join': 'round' },
      paint: {
        // Linhas perceptíveis sobre o mapa de risco, sem encobrir suas cores.
        'line-color': '#244a42',
        'line-opacity': ['interpolate', ['linear'], ['zoom'], 5, 0.66, 9, 0.85],
        'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.85, 8, 1.25, 12, 1.65],
      },
    },
    beforeId,
  )
}

export function setMunicipalBoundaryVisibility(
  map: MapLibreMap | null,
  visible: boolean,
) {
  if (map?.getLayer(MUNICIPAL_LINE_ID)) {
    map.setLayoutProperty(MUNICIPAL_LINE_ID, 'visibility', visible ? 'visible' : 'none')
  }
}
