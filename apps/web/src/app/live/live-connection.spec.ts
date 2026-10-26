import { TestBed } from '@angular/core/testing';
import { Subscription } from 'rxjs';

import { FakeWebSocket } from '../../testing/fake-web-socket';
import { telemetryEvent } from '../../testing/telemetry';
import { AuthService } from '../auth/auth.service';
import {
  LIVE_SOCKET_URL,
  LiveConnection,
  NOT_AUTHENTICATED,
  WEB_SOCKET_CTOR,
  reconnectDelayMs,
} from './live-connection';
import { LiveEvent } from './live-events';

describe('LiveConnection', () => {
  let connection: LiveConnection;
  let received: LiveEvent[];
  let subscription: Subscription | undefined;

  const auth = { refresh: vi.fn(), sessionExpired: vi.fn() };

  beforeEach(() => {
    FakeWebSocket.instances = [];
    received = [];
    auth.refresh.mockReset();
    auth.sessionExpired.mockReset();
    TestBed.configureTestingModule({
      providers: [
        { provide: LIVE_SOCKET_URL, useValue: 'ws://test/ws' },
        { provide: WEB_SOCKET_CTOR, useValue: FakeWebSocket },
        { provide: AuthService, useValue: auth },
      ],
    });
    connection = TestBed.inject(LiveConnection);
  });

  afterEach(() => {
    subscription?.unsubscribe();
    vi.useRealTimers();
  });

  function watchVessel(vesselId: string): void {
    subscription = connection
      .watch({ channel: 'vessel', vessel_id: vesselId })
      .subscribe((event) => received.push(event));
  }

  it('subscribes once the socket opens', () => {
    watchVessel('vessel-001');
    const socket = FakeWebSocket.latest();

    expect(socket.url).toBe('ws://test/ws');
    expect(connection.state()).toBe('connecting');

    socket.serverOpens();

    expect(connection.state()).toBe('open');
    expect(socket.sent).toEqual([
      { type: 'subscribe', channel: 'vessel', vessel_id: 'vessel-001' },
    ]);
  });

  it('only emits live events for the watched vessel', () => {
    watchVessel('vessel-001');
    const socket = FakeWebSocket.latest();
    socket.serverOpens();

    socket.serverSends({ type: 'subscribed', channel: 'vessel:vessel-001' });
    socket.serverSends(telemetryEvent({ vessel_id: 'vessel-002' }));
    socket.serverSends(telemetryEvent({ vessel_id: 'vessel-001' }));

    expect(received).toEqual([telemetryEvent({ vessel_id: 'vessel-001' })]);
  });

  it('unsubscribes when the caller stops watching', () => {
    watchVessel('vessel-001');
    const socket = FakeWebSocket.latest();
    socket.serverOpens();

    subscription?.unsubscribe();

    expect(socket.sent.at(-1)).toEqual({
      type: 'unsubscribe',
      channel: 'vessel',
      vessel_id: 'vessel-001',
    });
  });

  it('reconnects with backoff and subscribes again after the server closes', () => {
    vi.useFakeTimers();
    watchVessel('vessel-001');
    FakeWebSocket.latest().serverOpens();

    FakeWebSocket.latest().serverCloses();
    expect(connection.state()).toBe('reconnecting');
    expect(FakeWebSocket.instances).toHaveLength(1);

    vi.advanceTimersByTime(1000);
    expect(FakeWebSocket.instances).toHaveLength(2);

    const reconnected = FakeWebSocket.latest();
    reconnected.serverOpens();
    expect(connection.state()).toBe('open');
    expect(reconnected.sent).toEqual([
      { type: 'subscribe', channel: 'vessel', vessel_id: 'vessel-001' },
    ]);
  });

  it('refreshes the session before reconnecting when the token expired', async () => {
    auth.refresh.mockResolvedValue(true);
    watchVessel('vessel-001');
    FakeWebSocket.latest().serverOpens();

    FakeWebSocket.latest().serverCloses(NOT_AUTHENTICATED);
    await Promise.resolve();

    expect(auth.refresh).toHaveBeenCalledOnce();
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it('stops reconnecting when the session cannot be refreshed', async () => {
    auth.refresh.mockResolvedValue(false);
    watchVessel('vessel-001');
    FakeWebSocket.latest().serverOpens();

    FakeWebSocket.latest().serverCloses(NOT_AUTHENTICATED);
    await Promise.resolve();

    expect(auth.sessionExpired).toHaveBeenCalledOnce();
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});

describe('reconnectDelayMs', () => {
  it('doubles per attempt and is capped at 30 seconds', () => {
    const max = () => 1;

    expect([1, 2, 3, 4].map((attempt) => reconnectDelayMs(attempt, max))).toEqual([
      1000, 2000, 4000, 8000,
    ]);
    expect(reconnectDelayMs(10, max)).toBe(30_000);
  });

  it('adds jitter of up to half the delay', () => {
    expect(reconnectDelayMs(2, () => 0)).toBe(1000);
  });
});
