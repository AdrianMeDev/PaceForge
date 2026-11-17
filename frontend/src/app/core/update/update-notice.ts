import { DOCUMENT } from '@angular/common';
import { Component, InjectionToken, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { SwUpdate, VersionEvent } from '@angular/service-worker';
import { filter } from 'rxjs';

/** What "Reload" does; a token so that a spec does not have to leave the page. */
export const RELOAD_PAGE = new InjectionToken<() => void>('RELOAD_PAGE', {
  providedIn: 'root',
  factory: () => {
    const document = inject(DOCUMENT);
    return () => document.location.reload();
  },
});

/**
 * Says when a new version of the app is ready. The service worker keeps the app shell, so without
 * this a user would keep the old version until every tab is closed. Nothing is shown while the
 * service worker is off (`ng serve`, tests), or while no new version is there.
 */
@Component({
  selector: 'app-update-notice',
  template: `
    @if (message(); as text) {
      <div
        class="notice notice-warning flex flex-wrap items-center justify-between gap-2"
        role="status"
        data-testid="update-notice"
      >
        <span>{{ text }}</span>
        <button type="button" class="btn btn-secondary btn-sm" (click)="reload()">Reload</button>
      </div>
    }
  `,
})
export class UpdateNotice {
  private readonly updates = inject(SwUpdate, { optional: true });
  protected readonly reload = inject(RELOAD_PAGE);

  protected readonly message = signal<string | null>(null);

  constructor() {
    const updates = this.updates;
    if (updates?.isEnabled) {
      updates.versionUpdates
        .pipe(
          filter((event: VersionEvent) => event.type === 'VERSION_READY'),
          takeUntilDestroyed(),
        )
        .subscribe(() => this.message.set('A new version of PaceForge is ready.'));
      updates.unrecoverable
        .pipe(takeUntilDestroyed())
        .subscribe(() =>
          this.message.set('PaceForge could not update itself. Please reload the page.'),
        );
    }
  }
}
