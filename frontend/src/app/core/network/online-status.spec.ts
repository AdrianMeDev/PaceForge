import { TestBed } from '@angular/core/testing';
import { OnlineStatus } from './online-status';

describe('OnlineStatus', () => {
  afterEach(() => vi.restoreAllMocks());

  it('starts with what the browser says', () => {
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);

    expect(TestBed.inject(OnlineStatus).online()).toBe(false);
  });

  it('follows the events of the browser', () => {
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true);
    const status = TestBed.inject(OnlineStatus);
    expect(status.online()).toBe(true);

    window.dispatchEvent(new Event('offline'));
    expect(status.online()).toBe(false);

    window.dispatchEvent(new Event('online'));
    expect(status.online()).toBe(true);
  });
});
