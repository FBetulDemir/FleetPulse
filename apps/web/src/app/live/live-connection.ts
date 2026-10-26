import { DOCUMENT, InjectionToken, Service, inject, signal } from '@angular/core';
import { Observable, concat, retry, throwError, timer } from 'rxjs';
import { webSocket } from 'rxjs/webSocket';

import { ClientMessage, LiveChannel, LiveEvent, ServerMessage, isLiveEvent } from './live-events';

export type SocketState = 'connecting' | 'open' | 'reconnecting';

export const LIVE_SOCKET_URL = new InjectionToken<string>('LIVE_SOCKET_URL', {
  factory: () => {
    const { protocol, host } = inject(DOCUMENT).location;
    return `${protocol === 'https:' ? 'wss' : 'ws'}://${host}/ws`;
  },
});

/** Replaceable in tests with a fake WebSocket. */
export const WEB_SOCKET_CTOR = new InjectionToken<typeof WebSocket>('WEB_SOCKET_CTOR', {
  factory: () => WebSocket,
});

const MAX_BACKOFF_MS = 30_000;

/** Exponential backoff with jitter: about 1 s, 2 s, 4 s ... capped at 30 s. */
export function reconnectDelayMs(attempt: number, random = Math.random): number {
  const base = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** (attempt - 1));
  return Math.round(base * (0.5 + random() / 2));
}

/**
 * One shared WebSocket to the API.
 *
 * Each call to `watch()` subscribes to a channel over that socket. When the connection
 * drops, it reconnects with backoff and subscribes again automatically.
 */
@Service()
export class LiveConnection {
  private readonly stateSignal = signal<SocketState>('connecting');
  readonly state = this.stateSignal.asReadonly();

  private readonly socket = webSocket<ServerMessage | ClientMessage>({
    url: inject(LIVE_SOCKET_URL),
    WebSocketCtor: inject(WEB_SOCKET_CTOR),
    openObserver: { next: () => this.stateSignal.set('open') },
    closeObserver: { next: () => this.stateSignal.set('reconnecting') },
  });

  watch(channel: LiveChannel): Observable<LiveEvent> {
    const events = this.socket.multiplex(
      (): ClientMessage => ({ type: 'subscribe', ...channel }),
      (): ClientMessage => ({ type: 'unsubscribe', ...channel }),
      (message) =>
        isLiveEvent(message as ServerMessage) && belongsTo(message as LiveEvent, channel),
    ) as Observable<LiveEvent>;

    // A clean close (e.g. the API restarting) completes the stream instead of erroring.
    // Turning it into an error lets one retry rule handle every kind of disconnect.
    const closed = throwError(() => new Error('live connection closed'));
    return concat(events, closed).pipe(
      retry({
        delay: (_error, attempt) => timer(reconnectDelayMs(attempt)),
        resetOnSuccess: true,
      }),
    );
  }
}

function belongsTo(event: LiveEvent, channel: LiveChannel): boolean {
  return channel.channel === 'fleet' || event.vessel_id === channel.vessel_id;
}
