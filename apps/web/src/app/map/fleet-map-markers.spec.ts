import { row } from '../../testing/rows';
import {
  markerIcon,
  markerKey,
  markerLabel,
  markerPopup,
  markerShape,
  positioned,
} from './fleet-map-markers';

describe('fleet map markers', () => {
  it('only places vessels with a known position', () => {
    const rows = [row(), row({ vesselId: 'b', latitude: null, longitude: null })];

    expect(positioned(rows).map((r) => r.vesselId)).toEqual(['vessel-001']);
  });

  it('draws moving vessels as arrows pointing along their course, others as dots', () => {
    expect(markerShape(row())).toBe('arrow');
    expect(markerShape(row({ status: 'docked' }))).toBe('dot');
    expect(markerShape(row({ freshness: 'offline' }))).toBe('dot');

    expect(markerIcon(row({ courseDegrees: 142.4 })).style.transform).toBe('rotate(142deg)');
  });

  it('names the state in the label when a vessel is not live', () => {
    expect(markerLabel(row())).toBe('Älvskutt');
    expect(markerLabel(row({ freshness: 'offline' }))).toBe('Älvskutt · Offline');
  });

  it('rebuilds a marker only when its look changes, not on every small turn', () => {
    expect(markerKey(row({ courseDegrees: 141 }))).toBe(markerKey(row({ courseDegrees: 142 })));
    expect(markerKey(row())).not.toBe(markerKey(row({ freshness: 'stale' })));
  });

  it('treats vessel names as text, never as HTML', () => {
    const attack = '<img src=x onerror="alert(1)">';
    const popup = markerPopup(row({ name: attack }), () => undefined);

    expect(popup.querySelector('img')).toBeNull();
    expect(popup.textContent).toContain(attack);
  });

  it('opens the details page inside the app', () => {
    const open = vi.fn();
    const popup = markerPopup(row({ id: 'abc' }), open);

    popup.querySelector('a')!.click();

    expect(open).toHaveBeenCalledWith('abc');
  });
});
