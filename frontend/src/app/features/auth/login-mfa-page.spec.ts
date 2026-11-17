import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { MfaAuthenticateResult } from '../../core/auth/auth-models';
import { AuthStore } from '../../core/auth/auth-store';
import { createAuthStoreStub } from '../../core/auth/testing/auth-store-stub';
import { query, settle, typeInto } from '../../testing/dom';
import { LoginMfaPage } from './login-mfa-page';

describe('LoginMfaPage', () => {
  let store: ReturnType<typeof createAuthStoreStub>;
  let navigate: ReturnType<typeof vi.spyOn>;
  let navigateByUrl: ReturnType<typeof vi.spyOn>;
  let fixture: ComponentFixture<LoginMfaPage>;
  let page: HTMLElement;

  async function setup(params: Record<string, string> = {}): Promise<void> {
    store = createAuthStoreStub();
    store.logout.mockResolvedValue(undefined);
    TestBed.configureTestingModule({
      imports: [LoginMfaPage],
      providers: [
        provideRouter([]),
        { provide: AuthStore, useValue: store },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap(params) } },
        },
      ],
    });
    const router = TestBed.inject(Router);
    navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    navigateByUrl = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
    fixture = TestBed.createComponent(LoginMfaPage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  async function submit(code: string): Promise<void> {
    typeInto(page, '#code', code);
    query(page, 'form').dispatchEvent(new Event('submit'));
    await settle(fixture);
  }

  function answer(result: MfaAuthenticateResult): void {
    store.authenticateMfa.mockResolvedValue(result);
  }

  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((el) => (el.textContent ?? '').trim());
  const input = () => query<HTMLInputElement>(page, '#code');
  const submitButton = () => query<HTMLButtonElement>(page, 'button[type="submit"]');

  it('shows a labelled code field made for one-time codes and puts the cursor in it', async () => {
    await setup();

    expect(page.querySelector('label[for="code"]')).not.toBeNull();
    expect(input().autocomplete).toBe('one-time-code');
    expect(page.textContent).toContain('authenticator app');
    expect(page.textContent).toContain('recovery codes');
    expect(document.activeElement).toBe(input());
  });

  it('does not call the server without a code', async () => {
    await setup();

    await submit('   ');

    expect(store.authenticateMfa).not.toHaveBeenCalled();
    expect(query(page, '#code-error').textContent).toContain('Enter a code');
  });

  it.each([
    ['123456', '123456'],
    ['123 456', '123456'],
    ['  1234 5678 ', '12345678'],
  ])('sends %j as %j', async (typed, sent) => {
    await setup();
    answer({ kind: 'authenticated' });

    await submit(typed);

    expect(store.authenticateMfa).toHaveBeenCalledExactlyOnceWith(sent);
  });

  it('continues to the page the visitor wanted', async () => {
    await setup({ returnUrl: '/training/week' });
    answer({ kind: 'authenticated' });

    await submit('123456');

    expect(navigateByUrl).toHaveBeenCalledExactlyOnceWith('/training/week');
  });

  const unsafeTargets: Record<string, string>[] = [
    {},
    { returnUrl: '//evil.example.com' },
    { returnUrl: 'https://evil.example.com' },
  ];

  it.each(unsafeTargets)('goes to the start page for the return target %j', async (params) => {
    await setup(params);
    answer({ kind: 'authenticated' });

    await submit('123456');

    expect(navigateByUrl).toHaveBeenCalledExactlyOnceWith('/');
  });

  it('explains a wrong code, empties the field and keeps the cursor there', async () => {
    await setup();
    answer({
      kind: 'invalid',
      errors: [{ code: 'incorrect_code', message: 'raw', param: 'code' }],
    });

    await submit('000000');

    expect(alerts()).toEqual([
      'That code is not correct. Check the code in your authenticator app, or use a recovery code.',
    ]);
    expect(input().value).toBe('');
    expect(document.activeElement).toBe(input());
    expect(navigateByUrl).not.toHaveBeenCalled();
  });

  it('tells the visitor to wait after too many failed attempts', async () => {
    await setup();
    answer({
      kind: 'invalid',
      errors: [{ code: 'too_many_login_attempts', message: 'raw', param: 'code' }],
    });

    await submit('123456');

    expect(alerts()).toEqual([
      'Too many failed attempts. Please wait a few minutes and try again.',
    ]);
  });

  it('falls back to the server message for errors it does not know', async () => {
    await setup();
    answer({ kind: 'invalid', errors: [{ code: 'something_new', message: 'Account is locked.' }] });

    await submit('123456');

    expect(alerts()).toEqual(['Account is locked.']);
  });

  it('goes back to the password step with a notice when the sign-in has expired', async () => {
    await setup({ returnUrl: '/training' });
    answer({ kind: 'expired' });

    await submit('123456');

    expect(navigate).toHaveBeenCalledExactlyOnceWith(['/login'], {
      queryParams: { returnUrl: '/training', notice: 'sign-in-expired' },
    });
  });

  it('shows a generic message when the request fails unexpectedly', async () => {
    await setup();
    store.authenticateMfa.mockRejectedValue(new Error('network down'));

    await submit('123456');

    expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    expect(submitButton().disabled).toBe(false);
  });

  it('disables the button while the code is being checked', async () => {
    await setup();
    let finish!: (result: MfaAuthenticateResult) => void;
    store.authenticateMfa.mockReturnValue(
      new Promise<MfaAuthenticateResult>((resolve) => (finish = resolve)),
    );

    await submit('123456');
    expect(submitButton().disabled).toBe(true);
    expect(submitButton().textContent).toContain('Checking');

    finish({ kind: 'authenticated' });
    await settle(fixture);
    expect(navigateByUrl).toHaveBeenCalledTimes(1);
  });

  describe('giving up', () => {
    it('ends the half-finished sign-in and returns to the password step, keeping the target', async () => {
      await setup({ returnUrl: '/training' });

      query<HTMLButtonElement>(page, 'button.btn-ghost').click();
      await settle(fixture);

      expect(store.logout).toHaveBeenCalledTimes(1);
      expect(navigate).toHaveBeenCalledExactlyOnceWith(['/login'], {
        queryParams: { returnUrl: '/training' },
      });
    });

    it('returns to the password step even if ending the sign-in fails', async () => {
      await setup();
      store.logout.mockRejectedValue(new Error('network down'));

      query<HTMLButtonElement>(page, 'button.btn-ghost').click();
      await settle(fixture);

      expect(navigate).toHaveBeenCalledExactlyOnceWith(['/login'], { queryParams: {} });
    });
  });
});
