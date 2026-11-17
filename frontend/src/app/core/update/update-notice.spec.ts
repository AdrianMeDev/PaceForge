import { TestBed } from '@angular/core/testing';
import { SwUpdate, UnrecoverableStateEvent, VersionEvent } from '@angular/service-worker';
import { Subject } from 'rxjs';
import { query } from '../../testing/dom';
import { RELOAD_PAGE, UpdateNotice } from './update-notice';

describe('UpdateNotice', () => {
  let versions: Subject<VersionEvent>;
  let unrecoverable: Subject<UnrecoverableStateEvent>;
  let reload: ReturnType<typeof vi.fn<() => void>>;

  function show(enabled = true) {
    versions = new Subject<VersionEvent>();
    unrecoverable = new Subject<UnrecoverableStateEvent>();
    reload = vi.fn<() => void>();
    TestBed.configureTestingModule({
      providers: [
        {
          provide: SwUpdate,
          useValue: { isEnabled: enabled, versionUpdates: versions, unrecoverable },
        },
        { provide: RELOAD_PAGE, useValue: reload },
      ],
    });
    const fixture = TestBed.createComponent(UpdateNotice);
    fixture.detectChanges();
    return { fixture, page: fixture.nativeElement as HTMLElement };
  }

  const ready: VersionEvent = {
    type: 'VERSION_READY',
    currentVersion: { hash: 'a' },
    latestVersion: { hash: 'b' },
  };

  it('shows nothing until a new version is ready', () => {
    const { page } = show();

    expect(page.querySelector('[data-testid="update-notice"]')).toBeNull();
  });

  it('says when a new version is ready and reloads on request', () => {
    const { fixture, page } = show();

    versions.next(ready);
    fixture.detectChanges();

    expect(query(page, '[data-testid="update-notice"]').textContent).toContain(
      'A new version of PaceForge is ready.',
    );
    query<HTMLButtonElement>(page, 'button').click();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('ignores events that are no new version', () => {
    const { fixture, page } = show();

    versions.next({ type: 'VERSION_DETECTED', version: { hash: 'b' } });
    fixture.detectChanges();

    expect(page.querySelector('[data-testid="update-notice"]')).toBeNull();
  });

  it('asks for a reload when the service worker is in a state it cannot leave', () => {
    const { fixture, page } = show();

    unrecoverable.next({ type: 'UNRECOVERABLE_STATE', reason: 'broken' });
    fixture.detectChanges();

    expect(query(page, '[data-testid="update-notice"]').textContent).toContain('reload the page');
  });

  it('does nothing while the service worker is off', () => {
    const { fixture, page } = show(false);

    versions.next(ready);
    fixture.detectChanges();

    expect(page.querySelector('[data-testid="update-notice"]')).toBeNull();
  });

  it('works without any service worker provider at all', () => {
    TestBed.configureTestingModule({});
    const fixture = TestBed.createComponent(UpdateNotice);
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).querySelector('button')).toBeNull();
  });
});
