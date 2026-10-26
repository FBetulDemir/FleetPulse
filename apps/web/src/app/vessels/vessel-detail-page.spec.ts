import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Directive, input } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { NgxEchartsDirective } from 'ngx-echarts';
import { EMPTY } from 'rxjs';

import { telemetry } from '../../testing/telemetry';
import { registeredVessel } from '../../testing/vessels';
import { TelemetryHistory } from '../api/models';
import { LiveConnection } from '../live/live-connection';
import { VesselDetailPage } from './vessel-detail-page';

/** Stands in for ECharts, which needs a real canvas. */
// eslint-disable-next-line @angular-eslint/directive-selector -- must match ngx-echarts
@Directive({ selector: '[echarts]' })
class FakeEcharts {
  readonly options = input<unknown>();
}

const VESSEL = registeredVessel({ id: 'abc', name: 'Vinga Pilot', vessel_type: 'pilot' });
const BASE = '/api/v1/vessels/abc';

describe('VesselDetailPage', () => {
  let fixture: ComponentFixture<VesselDetailPage>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [VesselDetailPage],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: LiveConnection, useValue: { watch: () => EMPTY } },
      ],
    });
    TestBed.overrideComponent(VesselDetailPage, {
      remove: { imports: [NgxEchartsDirective] },
      add: { imports: [FakeEcharts] },
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(VesselDetailPage);
    fixture.componentRef.setInput('id', 'abc');
    TestBed.tick();
  });

  afterEach(() => http.verify());

  const page = () => fixture.nativeElement as HTMLElement;
  const tileValue = (label: string) =>
    [...page().querySelectorAll('.tile')]
      .find((tile) => tile.querySelector('dt')?.textContent?.trim() === label)
      ?.querySelector('dd')
      ?.textContent?.trim();

  async function load(latest = telemetry({ vessel_id: 'vessel-003' })) {
    http.expectOne(BASE).flush(VESSEL);
    http.expectOne(`${BASE}/telemetry/latest`).flush(latest);
    await fixture.whenStable();
  }

  it('shows the vessel and its last stored reading', async () => {
    await load(telemetry({ speed_knots: 7.3, battery_percent: 15, status: 'docked' }));

    expect(page().querySelector('h1')?.textContent).toBe('Vinga Pilot');
    expect(tileValue('Speed')).toBe('7.3 kn');
    expect(tileValue('Battery')).toContain('15 %');
    expect(tileValue('Battery')).toContain('low');
    expect(tileValue('Status')).toBe('docked');
  });

  it('says when the vessel does not exist', async () => {
    http.expectOne(BASE).flush(null, { status: 404, statusText: 'Not Found' });
    http
      .expectOne(`${BASE}/telemetry/latest`)
      .flush(null, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();

    expect(page().querySelector('h1')?.textContent).toBe('Vessel not found');
  });

  it('loads history only when the History tab is opened', async () => {
    await load();
    http.expectNone((request) => request.url.endsWith('/history'));

    const historyTab = [...page().querySelectorAll<HTMLElement>('[role="tab"]')].find((tab) =>
      tab.textContent?.includes('History'),
    );
    historyTab?.click();
    // The tab group reports the new tab in a microtask; the next tick sends the request.
    // (whenStable() would wait for that request, which only completes once flushed.)
    TestBed.tick();
    await new Promise((resolve) => setTimeout(resolve));
    TestBed.tick();

    const request = http.expectOne((r) => r.url === `${BASE}/telemetry/history`);
    expect(request.request.params.get('metric')).toBe('speed_knots');
    const from = Date.parse(request.request.params.get('from')!);
    const to = Date.parse(request.request.params.get('to')!);
    expect(to - from).toBe(3_600_000);

    const history: TelemetryHistory = {
      metric: 'speed_knots',
      start: new Date(from).toISOString(),
      end: new Date(to).toISOString(),
      bucket_seconds: 10,
      buckets: [{ time: new Date(from).toISOString(), avg: 5, min: 4, max: 6 }],
      summary: { avg: 5, min: 4, max: 6, count: 2 },
    };
    request.flush(history);
    await fixture.whenStable();

    expect(tileValue('Average')).toBe('5.0 kn');
    expect(tileValue('Readings')).toBe('2');
    expect(page().querySelector('.data-table tbody tr')?.textContent).toContain('6.0 kn');
  });
});
