import { DOCUMENT } from '@angular/common';
import { Injectable, inject, signal } from '@angular/core';

/**
 * Whether the browser says it has a connection. It is a hint: "online" only means that there is a
 * network, not that the server answers (the pages say so when a call fails). The app shell is
 * kept by the service worker, so the app opens without a connection and this says why nothing loads.
 */
@Injectable({ providedIn: 'root' })
export class OnlineStatus {
  private readonly window = inject(DOCUMENT).defaultView;

  private readonly state = signal(this.window?.navigator.onLine ?? true);
  /** `false` while the browser has no connection. */
  readonly online = this.state.asReadonly();

  constructor() {
    this.window?.addEventListener('online', () => this.state.set(true));
    this.window?.addEventListener('offline', () => this.state.set(false));
  }
}
