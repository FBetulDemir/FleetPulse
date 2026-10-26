import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { row } from '../../testing/rows';
import { VesselRow } from '../fleet/vessel-row';
import { FleetMap } from './fleet-map';

describe('FleetMap', () => {
  async function render(vessels: VesselRow[]) {
    TestBed.configureTestingModule({ imports: [FleetMap], providers: [provideRouter([])] });
    const fixture = TestBed.createComponent(FleetMap);
    fixture.componentRef.setInput('vessels', vessels);
    await fixture.whenStable();
    return fixture;
  }

  const labels = (host: HTMLElement) =>
    [...host.querySelectorAll('.fp-marker-label')].map((label) => label.textContent);

  it('places a labelled marker for every vessel with a position', async () => {
    const fixture = await render([
      row({ vesselId: 'a', name: 'Älvskutt' }),
      row({ vesselId: 'b', name: 'Vinga Pilot', freshness: 'offline' }),
      row({ vesselId: 'c', name: 'No position yet', latitude: null, longitude: null }),
    ]);
    const host = fixture.nativeElement as HTMLElement;

    expect(host.querySelectorAll('.fp-marker')).toHaveLength(2);
    expect(labels(host)).toEqual(['Älvskutt', 'Vinga Pilot · Offline']);
  });

  it('moves markers when positions change, and removes vessels that disappear', async () => {
    const fixture = await render([row({ vesselId: 'a' }), row({ vesselId: 'b', name: 'B' })]);

    fixture.componentRef.setInput('vessels', [row({ vesselId: 'a', latitude: 57.71 })]);
    await fixture.whenStable();

    const host = fixture.nativeElement as HTMLElement;
    expect(host.querySelectorAll('.fp-marker')).toHaveLength(1);
  });

  it('keeps an open popup open and current while the vessel updates', async () => {
    const fixture = await render([row({ vesselId: 'a', speedKnots: 5 })]);
    const host = fixture.nativeElement as HTMLElement;
    host.querySelector<HTMLElement>('.leaflet-marker-icon')!.click();
    expect(host.querySelector('.fp-popup')?.textContent).toContain('5.0 kn');

    // A turn and a state change used to replace the marker and close its popup.
    fixture.componentRef.setInput('vessels', [
      row({ vesselId: 'a', speedKnots: 6, courseDegrees: 300, freshness: 'stale' }),
    ]);
    await fixture.whenStable();

    expect(host.querySelector('.fp-popup')?.textContent).toContain('6.0 kn');
    expect(host.querySelector('.fp-popup')?.textContent).toContain('Stale');
  });
});
