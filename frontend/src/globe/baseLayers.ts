import * as maplibregl from 'maplibre-gl';

// Premium globe layers: Sentinel-2 satellite imagery, and topography (shaded
// relief everywhere, plus 3D terrain on capable devices). Both are raster
// layers slotted into the OpenFreeMap "liberty" base style at specific
// depths; see syncBaseLayers().

const SATELLITE_SOURCE_ID = 'satellite-imagery';
const SATELLITE_LAYER_ID = 'satellite-imagery-layer';
const HILLSHADE_SOURCE_ID = 'hillshade-dem';
const HILLSHADE_LAYER_ID = 'hillshade-relief';
const TERRAIN_SOURCE_ID = 'terrain-dem';

// EOX Sentinel-2 cloudless, 2016 edition. Deliberately the 2016 edition: it is
// global and released under CC BY 4.0 (commercial use allowed with
// attribution). EOX's 2018-and-later editions are CC BY-NC-SA (non-commercial
// only), and the 2017 edition is CC BY but incomplete — verified blank white
// land across much of Africa even at higher zooms.
const SATELLITE_TILES =
  'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/GoogleMapsCompatible/{z}/{y}/{x}.jpg';
const SATELLITE_ATTRIBUTION =
  '<a href="https://cloudless.eox.at" target="_blank" rel="noopener noreferrer">EOxCloudless</a> by EOX IT Services GmbH ' +
  '(Contains modified Copernicus Sentinel data 2016), ' +
  '<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">CC BY 4.0</a>';

// AWS Terrain Tiles (Mapzen/joerd), Terrarium encoding. Free; attribution required.
const DEM_TILES = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
const DEM_ATTRIBUTION =
  'Elevation: <a href="https://registry.opendata.aws/terrain-tiles/" target="_blank" rel="noopener noreferrer">Mapzen / AWS Terrain Tiles</a> ' +
  '(<a href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md" target="_blank" rel="noopener noreferrer">sources</a>)';

export interface BaseLayerState {
  satellite: boolean;
  relief: boolean;
  // 3D terrain mesh (relief only draws the shading). Off on phones/low-core devices.
  terrain3d: boolean;
}

function firstLayerId(map: maplibregl.Map, prefix: string): string | undefined {
  return map.getStyle().layers.find((layer) => layer.id.startsWith(prefix))?.id;
}

// Weather radar (radarLayer.ts) always draws above the imagery and the relief, whichever was switched on first, so the
// imagery and relief are slotted in below the first radar frame when there is one, and just below the borders when not.
function belowRadarOr(map: maplibregl.Map, fallback: string | undefined): string | undefined {
  return firstLayerId(map, 'radar-layer-') ?? fallback;
}

function removeLayerAndSource(map: maplibregl.Map, layerId: string | null, sourceId: string): void {
  if (layerId && map.getLayer(layerId)) map.removeLayer(layerId);
  if (map.getSource(sourceId)) map.removeSource(sourceId);
}

// Makes the map match `want`. Idempotent, so it can run on every state change.
//
// Layer order in the base style: fills/water -> roads/bridges -> buildings ->
// boundary_* -> labels. Imagery goes just below the first boundary layer: it
// covers fills, roads and buildings, but borders and labels stay on top.
// Hillshade goes below roads on the plain map (so it shades terrain, not
// streets), but just below boundaries when imagery is on (so it sits above
// the imagery instead of being hidden by it). Crisis pins are added last by
// crisisLayers.ts, so they always stay above everything here.
export function syncBaseLayers(map: maplibregl.Map, want: BaseLayerState): void {
  const boundaryAnchor = belowRadarOr(map, firstLayerId(map, 'boundary_'));

  if (want.satellite) {
    if (!map.getSource(SATELLITE_SOURCE_ID)) {
      map.addSource(SATELLITE_SOURCE_ID, {
        type: 'raster',
        tiles: [SATELLITE_TILES],
        tileSize: 256,
        // Native imagery is detailed to roughly here; MapLibre overzooms past it.
        maxzoom: 13,
        attribution: SATELLITE_ATTRIBUTION,
      });
    }
    if (!map.getLayer(SATELLITE_LAYER_ID)) {
      map.addLayer({ id: SATELLITE_LAYER_ID, type: 'raster', source: SATELLITE_SOURCE_ID }, boundaryAnchor);
    } else if (firstLayerId(map, 'radar-layer-')) {
      // Radar was added after the imagery, or the imagery is redrawn: keep the imagery under it.
      map.moveLayer(SATELLITE_LAYER_ID, boundaryAnchor);
    }
  } else {
    removeLayerAndSource(map, SATELLITE_LAYER_ID, SATELLITE_SOURCE_ID);
  }

  if (want.relief) {
    if (!map.getSource(HILLSHADE_SOURCE_ID)) {
      map.addSource(HILLSHADE_SOURCE_ID, {
        type: 'raster-dem',
        tiles: [DEM_TILES],
        encoding: 'terrarium',
        tileSize: 256,
        maxzoom: 12,
        attribution: DEM_ATTRIBUTION,
      });
    }
    const anchor = want.satellite ? boundaryAnchor : firstLayerId(map, 'aeroway');
    if (!map.getLayer(HILLSHADE_LAYER_ID)) {
      map.addLayer({ id: HILLSHADE_LAYER_ID, type: 'hillshade', source: HILLSHADE_SOURCE_ID }, anchor);
    } else {
      map.moveLayer(HILLSHADE_LAYER_ID, anchor);
    }
    // Lighter over imagery, which already has its own shading.
    map.setPaintProperty(HILLSHADE_LAYER_ID, 'hillshade-exaggeration', want.satellite ? 0.35 : 0.6);

    if (want.terrain3d) {
      // A separate DEM source for the mesh, as MapLibre recommends.
      if (!map.getSource(TERRAIN_SOURCE_ID)) {
        map.addSource(TERRAIN_SOURCE_ID, {
          type: 'raster-dem',
          tiles: [DEM_TILES],
          encoding: 'terrarium',
          tileSize: 256,
          maxzoom: 12,
        });
      }
      map.setTerrain({ source: TERRAIN_SOURCE_ID, exaggeration: 1.4 });
    } else {
      removeTerrain(map);
    }
  } else {
    removeTerrain(map);
    removeLayerAndSource(map, HILLSHADE_LAYER_ID, HILLSHADE_SOURCE_ID);
  }
}

// The terrain must be detached before its source can be removed.
function removeTerrain(map: maplibregl.Map): void {
  if (map.getTerrain()) map.setTerrain(null);
  if (map.getSource(TERRAIN_SOURCE_ID)) map.removeSource(TERRAIN_SOURCE_ID);
}
