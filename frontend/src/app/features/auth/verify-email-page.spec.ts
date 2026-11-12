import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { AuthApi } from '../../core/auth/auth-api';
import { EmailVerificationInfo, VerifyEmailResult } from '../../core/auth/auth-models';
import { AuthStore } from '../../core/auth/auth-store';
import { createAuthStoreStub } from '../../core/auth/testing/auth-store-stub';
import { query, settle } from '../../testing/dom';
import { VerifyEmailPage } from './verify-email-page';

const KEY = 'MQ:1xRY3y:abc-_';
const VALID: EmailVerificationInfo = { kind: 'valid', email: 'ann@example.com' };
const INVALID: EmailVerificationInfo = {
  kind: 'invalid',
  errors: [{ code: 'invalid_or_expired_key', message: 'Expired.', param: 'key' }],
};

describe('VerifyEmailPage', () => {
  let getEmailVerification: ReturnType<
    typeof vi.fn<(key: string) => Promise<EmailVerificationInfo>>
  >;
  let store: ReturnType<typeof createAuthStoreStub>;
  let fixture: ComponentFixture<VerifyEmailPage>;
  let page: HTMLElement;

  /**
   * Creates the page; `info` is what the server says about the link. `prepare` can queue
   * different answers before the page asks for the first time.
   */
  async function setup(
    info: Promise<EmailVerificationInfo> | EmailVerificationInfo = VALID,
    prepare?: (lookup: typeof getEmailVerification) => void,
  ) {
    getEmailVerification = vi.fn<(key: string) => Promise<EmailVerificationInfo>>();
    getEmailVerification.mockReturnValue(Promise.resolve(info));
    prepare?.(getEmailVerification);
    store = createAuthStoreStub();
    TestBed.configureTestingModule({
      imports: [VerifyEmailPage],
      providers: [
        provideRouter([]),
        { provide: AuthApi, useValue: { getEmailVerification } },
        { provide: AuthStore, useValue: store },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ key: KEY }) } },
        },
      ],
    });
    fixture = TestBed.createComponent(VerifyEmailPage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  const text = () => (page.textContent ?? '').replace(/\s+/g, ' ').trim();
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((el) => (el.textContent ?? '').trim());
  const button = () => query<HTMLButtonElement>(page, 'button');

  async function confirmWith(result: VerifyEmailResult | Promise<VerifyEmailResult>) {
    store.verifyEmail.mockReturnValue(Promise.resolve(result));
    button().click();
    await settle(fixture);
  }

  it('says it is checking the link while the server has not answered', async () => {
    await setup(new Promise<EmailVerificationInfo>(() => undefined));

    expect(query(page, '[role="status"]').textContent).toContain('Checking your link');
    expect(page.querySelector('button')).toBeNull();
  });

  it('shows the address the link is for and waits for the click', async () => {
    await setup();

    expect(text()).toContain('ann@example.com');
    expect(button().textContent).toContain('Confirm email address');
    expect(store.verifyEmail).not.toHaveBeenCalled();
  });

  it('looks the link up with the decoded route parameter and confirms with the same key', async () => {
    await setup();

    await confirmWith({ kind: 'verified' });

    expect(getEmailVerification).toHaveBeenCalledExactlyOnceWith(KEY);
    expect(store.verifyEmail).toHaveBeenCalledExactlyOnceWith(KEY);
  });

  it('confirms and offers the sign-in when the visitor is not signed in', async () => {
    await setup();

    await confirmWith({ kind: 'verified' });

    expect(query(page, '[role="status"]').textContent).toContain('ann@example.com');
    expect(query(page, '[role="status"]').textContent).toContain('is confirmed');
    const link = query<HTMLAnchorElement>(page, 'a');
    expect(link.getAttribute('href')).toBe('/login');
    expect(link.textContent).toContain('Go to sign in');
    expect(page.querySelector('button')).toBeNull();
  });

  it('continues to the app when the confirmation also signed the visitor in', async () => {
    await setup();

    await confirmWith({ kind: 'authenticated' });

    const link = query<HTMLAnchorElement>(page, 'a');
    expect(link.getAttribute('href')).toBe('/');
    expect(link.textContent).toContain('Continue');
  });

  it('continues to the app when the visitor was already signed in', async () => {
    await setup();
    store.signIn();

    await confirmWith({ kind: 'verified' });

    expect(query<HTMLAnchorElement>(page, 'a').getAttribute('href')).toBe('/');
  });

  it('explains an invalid or expired link without a confirm button', async () => {
    await setup(INVALID);

    expect(alerts()).toEqual(['This confirmation link is invalid or has expired.']);
    expect(text()).toContain('we will send you a new link');
    expect(page.querySelector('button')).toBeNull();
    expect(query<HTMLAnchorElement>(page, 'a').getAttribute('href')).toBe('/login');
  });

  it('shows the same explanation when the link expires between look-up and click', async () => {
    await setup();

    await confirmWith({ kind: 'invalid', errors: INVALID.errors });

    expect(alerts()).toEqual(['This confirmation link is invalid or has expired.']);
  });

  it('offers to try again when the link cannot be checked, then recovers', async () => {
    await setup(VALID, (lookup) => {
      lookup.mockRejectedValueOnce(new Error('network down')).mockResolvedValueOnce(VALID);
    });
    expect(alerts()).toEqual(['We could not check the link. Please try again.']);

    button().click();
    await settle(fixture);

    expect(getEmailVerification).toHaveBeenCalledTimes(2);
    expect(text()).toContain('ann@example.com');
    expect(alerts()).toEqual([]);
  });

  it('keeps the button and shows a message when confirming fails unexpectedly', async () => {
    await setup();
    store.verifyEmail.mockRejectedValue(new Error('boom'));

    button().click();
    await settle(fixture);

    expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    expect(button().disabled).toBe(false);
  });

  it('disables the button while the address is being confirmed', async () => {
    await setup();
    let finish!: (result: VerifyEmailResult) => void;
    store.verifyEmail.mockReturnValue(
      new Promise<VerifyEmailResult>((resolve) => (finish = resolve)),
    );

    button().click();
    await settle(fixture);
    expect(button().disabled).toBe(true);
    expect(button().textContent).toContain('Confirming');
    button().click();
    expect(store.verifyEmail).toHaveBeenCalledTimes(1);

    finish({ kind: 'verified' });
    await settle(fixture);
    expect(page.querySelector('button')).toBeNull();
  });
});
