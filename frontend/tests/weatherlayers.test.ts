// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  cloudTileUrl, fieldLegendUrl, fieldTileUrl, fireTileUrl, formatForecastTime, nearestTime, relativeHours, todayUtc, yesterdayUtc,
} from '../src/globe/weatherLayers.ts';

const TIMES = ['2026-10-08T06:00:00Z', '2026-10-08T07:00:00Z', '2026-10-08T08:00:00Z', '2026-10-09T08:00:00Z'];

describe('nearestTime', () => {
  it('picks the forecast hour closest to a moment', () => {
    assert.equal(nearestTime(TIMES, Date.parse('2026-10-08T07:20:00Z')), '2026-10-08T07:00:00Z');
    assert.equal(nearestTime(TIMES, Date.parse('2026-10-08T07:40:00Z')), '2026-10-08T08:00:00Z');
  });

  it('clamps to the ends of what the model has', () => {
    assert.equal(nearestTime(TIMES, Date.parse('2026-09-01T00:00:00Z')), TIMES[0]);
    assert.equal(nearestTime(TIMES, Date.parse('2027-01-01T00:00:00Z')), TIMES[3]);
  });

  it('has nothing for an empty list', () => {
    assert.equal(nearestTime([], 0), null);
    assert.equal(nearestTime(undefined, 0), null);
  });
});

describe('tile addresses', () => {
  it('asks DWD for the layer at the forecast hour in the form MapLibre fills in', () => {
    const url = fieldTileUrl('Icon_reg025_fd_sl_T2M', '2026-10-08T07:00:00Z');
    assert.match(url, /^https:\/\/maps\.dwd\.de\/geoserver\/dwd\/wms\?/);
    assert.ok(url.includes('layers=dwd:Icon_reg025_fd_sl_T2M') && url.includes('bbox={bbox-epsg-3857}') && url.includes('crs=EPSG:3857'));
    assert.ok(url.includes('time=2026-10-08T07%3A00%3A00Z') && url.includes('transparent=true'));
  });

  it('points at the legend picture and the NASA tiles', () => {
    assert.ok(fieldLegendUrl('X').includes('request=GetLegendGraphic') && fieldLegendUrl('X').includes('layer=dwd:X'));
    assert.ok(cloudTileUrl('2026-10-07').includes('MODIS_Terra_Cloud_Fraction_Day/default/2026-10-07/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png'));
    const fires = fireTileUrl('2026-10-08');
    assert.ok(fires.includes('/wms/epsg3857/best/wms.cgi') && fires.includes('LAYERS=VIIRS_SNPP_Thermal_Anomalies_375m_All'));
    assert.ok(fires.includes('BBOX={bbox-epsg-3857}') && fires.endsWith('TIME=2026-10-08'));
  });
});

describe('dates and labels', () => {
  it("yesterday in UTC is the newest complete daily composite", () => {
    assert.equal(yesterdayUtc(Date.parse('2026-10-08T00:30:00Z')), '2026-10-07');
    assert.equal(yesterdayUtc(Date.parse('2026-03-01T23:59:00Z')), '2026-02-28');
  });

  it("today's date in UTC is the fire layer's day", () => {
    assert.equal(todayUtc(Date.parse('2026-10-08T23:59:00Z')), '2026-10-08');
  });

  it('labels a forecast hour in UTC and says how far away it is', () => {
    assert.equal(formatForecastTime('2026-10-10T15:00:00Z'), 'Sat 10 Oct, 15:00 UTC');
    const now = Date.parse('2026-10-09T21:00:00Z');
    assert.equal(relativeHours('2026-10-10T15:00:00Z', now), 'in 18 h');
    assert.equal(relativeHours('2026-10-09T15:00:00Z', now), '6 h ago');
    assert.equal(relativeHours('2026-10-09T21:10:00Z', now), 'now');
  });
});
