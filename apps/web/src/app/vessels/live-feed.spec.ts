import { Injector, runInInjectionContext, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';

import { telemetry } from '../../testing/telemetry';
import { LiveConnection } from '../live/live-connection';
import { LiveChannel, LiveEvent } from '../live/live-events';
import { LIVE_WINDOW_MS, appendReading, liveFeed } from './live-feed';

const at = (seconds: number) => new Date(Date.UTC(2026, 9, 26, 10, 0, seconds)).toISOString();

describe('appendReading', () => {
  it('keeps readings in time order and ignores repeats', () => {
    const first = telemetry({ timestamp: at(1) });
    const second = telemetry({ timestamp: at(2) });

    let readings = appendReading([], first);
    readings = appendReading(readings, second);
    readings = appendReading(readings, first); // resent after a reconnect

    expect(readings).toEqual([first, second]);
  });

  it('drops readings older than the window', () => {
    const old = telemetry({ timestamp: at(0) });
    const recent = telemetry({ timestamp: at(30) });

    expect(appendReading([old], recent, 10_000)).toEqual([recent]);
    expect(LIVE_WINDOW_MS).toBe(300_000);
  });
});

describe('liveFeed', () => {
  it('follows the given vessel and tracks readings and connection state', () => {
    const events = new Subject<LiveEvent>();
    const watched: LiveChannel[] = [];
    TestBed.configureTestingModule({
      providers: [
        {
          provide: LiveConnection,
          useValue: {
            watch: (channel: LiveChannel) => {
              watched.push(channel);
              return events;
            },
          },
        },
      ],
    });
    const vesselId = signal<string | undefined>(undefined);
    const feed = runInInjectionContext(TestBed.inject(Injector), () => liveFeed(vesselId));

    vesselId.set('vessel-001');
    TestBed.tick();
    events.next({ type: 'vessel_status', vessel_id: 'vessel-001', state: 'online' });
    events.next({
      type: 'telemetry',
      vessel_id: 'vessel-001',
      data: telemetry({ timestamp: at(1) }),
    });
    events.next({
      type: 'telemetry',
      vessel_id: 'vessel-001',
      data: telemetry({ timestamp: at(2), speed_knots: 9 }),
    });

    expect(watched).toEqual([{ channel: 'vessel', vessel_id: 'vessel-001' }]);
    expect(feed.connection()).toBe('online');
    expect(feed.readings()).toHaveLength(2);
    expect(feed.latest()?.speed_knots).toBe(9);
  });
});
