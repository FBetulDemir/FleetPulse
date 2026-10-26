import { DOCUMENT, InjectionToken, Service, inject, signal } from '@angular/core';
import { EMPTY, Observable, concat, from, of, retry, switchMap, throwError, timer } from 'rxjs';
import { webSocket } from 'rxjs/webSocket';

import { AuthService } from '../auth/auth.service';
import { ClientMessage, LiveChannel, LiveEvent, ServerMessage, isLiveEvent } from './live-events';

/** Close code the API uses when the WebSocket is not authenticated (like HTTP 401). */
export const NOT_AUTHENTICATED = 4401;

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
 * drops, it reconnects with backoff and subscribes again automatically. If the server
 * closes it because the access token expired, it refreshes the session first.
 */
@Service()
export class LiveConnection {
  private readonly auth = inject(AuthService);
  private readonly stateSignal = signal<SocketState>('connecting');
  readonly state = this.stateSignal.asReadonly();

  private lastCloseCode: number | null = null;

  private readonly socket = webSocket<ServerMessage | ClientMessage>({
    url: inject(LIVE_SOCKET_URL),
    WebSocketCtor: inject(WEB_SOCKET_CTOR),
    openObserver: {
      next: () => {
        this.lastCloseCode = null;
        this.stateSignal.set('open');
      },
    },
    closeObserver: {
      next: (event) => {
        this.lastCloseCode = event.code;
        this.stateSignal.set('reconnecting');
      },
    },
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
      retry({ delay: (_error, attempt) => this.beforeReconnect(attempt), resetOnSuccess: true }),
    );
  }

  /** Emits when it is time to reconnect; completing instead stops reconnecting. */
  private beforeReconnect(attempt: number): Observable<unknown> {
    if (this.lastCloseCode !== NOT_AUTHENTICATED) return timer(reconnectDelayMs(attempt));
    return from(this.auth.refresh()).pipe(
      switchMap((refreshed) => {
        if (refreshed) return of(true);
        this.auth.sessionExpired();
        return EMPTY;
      }),
    );
  }
}

function belongsTo(event: LiveEvent, channel: LiveChannel): boolean {
  return channel.channel === 'fleet' || event.vessel_id === channel.vessel_id;
}
