/** Minimal stand-in for the browser WebSocket, driven by the test. */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  static latest(): FakeWebSocket {
    const socket = FakeWebSocket.instances.at(-1);
    if (!socket) throw new Error('no WebSocket was created');
    return socket;
  }

  readyState = 0;
  binaryType = 'blob';
  readonly sent: unknown[] = [];
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data));
  }

  close(): void {
    this.readyState = 3;
  }

  // Test controls

  serverOpens(): void {
    this.readyState = 1;
    this.onopen?.(new Event('open'));
  }

  serverSends(message: unknown): void {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(message) }));
  }

  serverCloses(): void {
    this.readyState = 3;
    this.onclose?.(new CloseEvent('close', { wasClean: true, code: 1012 }));
  }
}
