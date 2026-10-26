import { DestroyRef, Service, inject, signal } from '@angular/core';

export type Scheme = 'light' | 'dark';

/** The operating system's light/dark preference, kept up to date while the app runs. */
@Service()
export class ColorScheme {
  private readonly query =
    typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: dark)') : null;
  private readonly schemeSignal = signal<Scheme>(this.query?.matches ? 'dark' : 'light');
  readonly scheme = this.schemeSignal.asReadonly();

  constructor() {
    const update = (event: MediaQueryListEvent) =>
      this.schemeSignal.set(event.matches ? 'dark' : 'light');
    this.query?.addEventListener('change', update);
    inject(DestroyRef).onDestroy(() => this.query?.removeEventListener('change', update));
  }
}
