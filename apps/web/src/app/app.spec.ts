import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { App } from './app';
import { LiveConnection, SocketState } from './live/live-connection';

describe('App', () => {
  const state = signal<SocketState>('connecting');

  async function render(): Promise<HTMLElement> {
    TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter([]), { provide: LiveConnection, useValue: { state } }],
    });
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  it('labels the data as simulated', async () => {
    const page = await render();

    expect(page.textContent).toContain('Simulated data');
  });

  it('announces the live connection state', async () => {
    state.set('reconnecting');
    const page = await render();

    const status = page.querySelector('.socket[role="status"]');
    expect(status?.textContent).toContain('Reconnecting');
  });
});
