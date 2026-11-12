import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { LoginOutcome } from '../../core/auth/auth-models';
import { AuthStore } from '../../core/auth/auth-store';
import { createAuthStoreStub } from '../../core/auth/testing/auth-store-stub';
import { LoginPage, safeReturnUrl } from './login-page';
import { query } from '../../testing/dom';

describe('safeReturnUrl', () => {
  it.each(['/training', '/training/week?day=2', '/'])('keeps the in-app path %s', (url) => {
    expect(safeReturnUrl(url)).toBe(url);
  });

  it.each([
    null,
    '',
    'training',
    '//evil.example.com',
    'https://evil.example.com',
    'javascript:alert(1)',
  ])('falls back to the start page for %s', (url) => {
    expect(safeReturnUrl(url)).toBe('/');
  });
});

describe('LoginPage', () => {
  let store: ReturnType<typeof createAuthStoreStub>;
  let navigate: ReturnType<typeof vi.spyOn>;
  let fixture: ComponentFixture<LoginPage>;
  let page: HTMLElement;

  async function setup(query: Record<string, string> = {}): Promise<void> {
    store = createAuthStoreStub();
    TestBed.configureTestingModule({
      imports: [LoginPage],
      providers: [
        provideRouter([]),
        { provide: AuthStore, useValue: store },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap(query) } },
        },
      ],
    });
    navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture = TestBed.createComponent(LoginPage);
    page = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
  }

  function type(id: string, value: string): void {
    const input = query<HTMLInputElement>(page, `#${id}`);
    input.value = value;
    input.dispatchEvent(new Event('input'));
  }

  /** Submits the form and lets the async handler and the following change detection finish. */
  async function submit(email = 'ada@example.com', password = 'secret'): Promise<void> {
    type('email', email);
    type('password', password);
    query(page, 'form').dispatchEvent(new Event('submit'));
    await settle();
  }

  async function settle(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();
  }

  function alerts(): string[] {
    return Array.from(page.querySelectorAll('[role="alert"]')).map((el) =>
      (el.textContent ?? '').trim(),
    );
  }

  function respondWith(outcome: LoginOutcome): void {
    store.login.mockResolvedValue(outcome);
  }

  it('shows labelled email and password fields', async () => {
    await setup();

    expect(page.querySelector('label[for="email"]')).not.toBeNull();
    expect(page.querySelector('input#email[type="email"]')).not.toBeNull();
    expect(page.querySelector('label[for="password"]')).not.toBeNull();
    expect(page.querySelector('input#password[type="password"]')).not.toBeNull();
  });

  it('does not call the server for an incomplete form and explains what is missing', async () => {
    await setup();

    await submit('not-an-email', '');

    expect(store.login).not.toHaveBeenCalled();
    expect(page.querySelector('#email-error')?.textContent).toContain('valid email');
    expect(page.querySelector('#password-error')?.textContent).toContain('password');
  });

  it('signs in and returns to the page the visitor wanted', async () => {
    await setup({ returnUrl: '/training/week' });
    respondWith({ kind: 'success' });

    await submit();

    expect(store.login).toHaveBeenCalledWith('ada@example.com', 'secret');
    expect(navigate).toHaveBeenCalledWith('/training/week');
  });

  it('goes to the start page when there is no return target', async () => {
    await setup();
    respondWith({ kind: 'success' });

    await submit();

    expect(navigate).toHaveBeenCalledWith('/');
  });

  it('ignores a return target that leaves the app', async () => {
    await setup({ returnUrl: '//evil.example.com' });
    respondWith({ kind: 'success' });

    await submit();

    expect(navigate).toHaveBeenCalledWith('/');
  });

  it('shows a clear message for wrong credentials and allows another try', async () => {
    await setup();
    respondWith({
      kind: 'invalid',
      errors: [{ code: 'email_password_mismatch', message: 'raw server text', param: 'password' }],
    });

    await submit('ada@example.com', 'wrong');

    expect(alerts()).toEqual(['The email address or the password is not correct.']);
    expect(navigate).not.toHaveBeenCalled();
    expect(query<HTMLButtonElement>(page, 'button[type="submit"]').disabled).toBe(false);
  });

  it('tells the visitor to wait after too many failed attempts', async () => {
    await setup();
    respondWith({
      kind: 'invalid',
      errors: [{ code: 'too_many_login_attempts', message: 'raw server text' }],
    });

    await submit();

    expect(alerts()).toEqual([
      'Too many failed attempts. Please wait a few minutes and try again.',
    ]);
  });

  it('falls back to the server message for errors it does not know', async () => {
    await setup();
    respondWith({
      kind: 'invalid',
      errors: [{ code: 'something_new', message: 'Account is locked.' }],
    });

    await submit();

    expect(alerts()).toEqual(['Account is locked.']);
  });

  it('asks to verify the email address when that flow is pending', async () => {
    await setup();
    respondWith({ kind: 'pending', flows: [{ id: 'verify_email', is_pending: true }] });

    await submit();

    expect(page.querySelector('[role="status"]')?.textContent).toContain('verify your email');
    expect(alerts()).toEqual([]);
    expect(navigate).not.toHaveBeenCalled();
  });

  it('reports sign-in steps that are not supported yet', async () => {
    await setup();
    respondWith({ kind: 'pending', flows: [{ id: 'mfa_authenticate', is_pending: true }] });

    await submit();

    expect(alerts()).toEqual(['This account needs a sign-in step that is not supported yet.']);
    expect(navigate).not.toHaveBeenCalled();
  });

  it('shows a generic message when the request fails unexpectedly', async () => {
    await setup();
    store.login.mockRejectedValue(new Error('network down'));

    await submit();

    expect(alerts()).toEqual(['Something went wrong. Please try again.']);
  });

  it('disables the button while signing in', async () => {
    await setup();
    let finish!: (outcome: LoginOutcome) => void;
    store.login.mockReturnValue(new Promise<LoginOutcome>((resolve) => (finish = resolve)));

    await submit();
    const button = query<HTMLButtonElement>(page, 'button[type="submit"]');
    expect(button.disabled).toBe(true);
    expect(button.textContent).toContain('Signing in');

    finish({ kind: 'success' });
    await settle();
    expect(button.disabled).toBe(false);
  });

  it('warns when the server cannot be reached', async () => {
    await setup();
    store.setStatus('unavailable');
    await fixture.whenStable();

    expect(alerts()).toEqual(['The server cannot be reached right now. Please try again later.']);
  });
});
