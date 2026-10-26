import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { telemetry } from '../../testing/telemetry';
import { FleetLiveStore, VesselLiveState } from '../live/fleet-live-store';
import { FleetPage } from './fleet-page';

describe('FleetPage', () => {
  const vessels = signal<VesselLiveState[]>([]);

  async function render(): Promise<HTMLElement> {
    TestBed.configureTestingModule({
      imports: [FleetPage],
      providers: [{ provide: FleetLiveStore, useValue: { vessels } }],
    });
    const fixture = TestBed.createComponent(FleetPage);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  beforeEach(() => vessels.set([]));

  it('shows a waiting state before any vessel reports', async () => {
    const page = await render();

    expect(page.querySelector('[role="status"]')?.textContent).toContain('Waiting for vessel data');
    expect(page.querySelector('table')).toBeNull();
  });

  it('renders one row per vessel with its latest readings', async () => {
    vessels.set([
      { vesselId: 'vessel-001', connection: 'online', telemetry: telemetry() },
      {
        vesselId: 'vessel-002',
        connection: 'offline',
        telemetry: telemetry({ vessel_id: 'vessel-002', battery_percent: 12 }),
      },
    ]);

    const page = await render();
    const rows = [...page.querySelectorAll('tbody tr')].map((row) => row.textContent ?? '');

    expect(rows).toHaveLength(2);
    expect(rows[0]).toContain('vessel-001');
    expect(rows[0]).toContain('8.2 kn');
    expect(rows[0]).toContain('76 %');
    expect(rows[1]).toContain('Offline');
    expect(rows[1]).toContain('12 %');
    expect(rows[1]).toContain('low');
  });
});
