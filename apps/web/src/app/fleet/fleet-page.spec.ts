import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { telemetry } from '../../testing/telemetry';
import { registeredVessel, vesselPage } from '../../testing/vessels';
import { FleetLiveStore, VesselLiveState } from '../live/fleet-live-store';
import { FleetPage, VESSELS_URL } from './fleet-page';

describe('FleetPage', () => {
  const live = signal<VesselLiveState[]>([]);
  let fixture: ComponentFixture<FleetPage>;
  let http: HttpTestingController;

  beforeEach(async () => {
    live.set([]);
    TestBed.configureTestingModule({
      imports: [FleetPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    // The page provides its own store, so replace it at the component level.
    TestBed.overrideComponent(FleetPage, {
      set: { providers: [{ provide: FleetLiveStore, useValue: { vessels: live } }] },
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(FleetPage);
    // Runs effects so the registry request is sent. (whenStable() would wait for the
    // pending request, which only completes when a test flushes it.)
    TestBed.tick();
  });

  afterEach(() => http.verify());

  function page(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function rowTexts(): string[] {
    return [...page().querySelectorAll('tbody tr')].map((row) => row.textContent ?? '');
  }

  async function respondWithRegistry(...vessels: ReturnType<typeof registeredVessel>[]) {
    TestBed.tick(); // sends any request scheduled since the last tick, e.g. after Retry
    http.expectOne(VESSELS_URL).flush(vesselPage(vessels));
    await fixture.whenStable();
  }

  it('shows a waiting state before any vessel is known', async () => {
    await respondWithRegistry();

    expect(page().querySelector('[role="status"]')?.textContent).toContain(
      'Waiting for vessel data',
    );
    expect(page().querySelector('table')).toBeNull();
  });

  it('shows registered vessels with their live readings', async () => {
    live.set([
      {
        vesselId: 'vessel-001',
        connection: 'online',
        // A current reading, so the vessel counts as live rather than stale.
        telemetry: telemetry({ timestamp: new Date().toISOString() }),
      },
      {
        vesselId: 'vessel-002',
        connection: 'offline',
        telemetry: telemetry({ vessel_id: 'vessel-002', battery_percent: 12 }),
      },
    ]);
    await respondWithRegistry(
      registeredVessel({ identifier: 'vessel-001', name: 'Älvskutt' }),
      registeredVessel({ identifier: 'vessel-002', name: 'Hönö Runner', vessel_type: 'workboat' }),
    );

    const rowFor = (name: string) => rowTexts().find((text) => text.includes(name)) ?? '';
    expect(rowTexts()).toHaveLength(2);
    expect(rowFor('Hönö Runner')).toContain('workboat');
    expect(rowFor('Hönö Runner')).toContain('Offline');
    expect(rowFor('Hönö Runner')).toContain('12 %');
    expect(rowFor('Hönö Runner')).toContain('low');
    expect(rowFor('Älvskutt')).toContain('vessel-001');
    expect(rowFor('Älvskutt')).toContain('8.2 kn');
    // Key figures summarise the same rows.
    const kpi = (label: string) =>
      [...page().querySelectorAll('.kpi')]
        .find((k) => k.querySelector('dt')?.textContent?.trim() === label)
        ?.querySelector('dd')
        ?.textContent?.replace(/\s+/g, ' ')
        .trim();
    expect(kpi('Vessels')).toBe('2');
    expect(kpi('Reporting live')).toBe('1 of 2');
    expect(kpi('Offline or stale')).toBe('warning 1');
    expect(kpi('Average battery')).toBe('44 % 1 low');
    // Registered vessels link to their detail page.
    const link = page().querySelector<HTMLAnchorElement>('a.vessel-name');
    expect(link?.getAttribute('href')).toMatch(/^\/vessels\//);
  });

  it('keeps showing live data and offers a retry when the registry fails', async () => {
    live.set([{ vesselId: 'vessel-001', connection: 'online', telemetry: telemetry() }]);
    http.expectOne(VESSELS_URL).flush(null, { status: 503, statusText: 'Service Unavailable' });
    await fixture.whenStable();

    expect(page().querySelector('[role="alert"]')?.textContent).toContain('could not be loaded');
    expect(rowTexts()[0]).toContain('vessel-001');

    page().querySelector<HTMLButtonElement>('[role="alert"] button')?.click();
    await respondWithRegistry(registeredVessel());

    expect(page().querySelector('[role="alert"]')).toBeNull();
    expect(rowTexts()[0]).toContain('Älvskutt');
  });
});
