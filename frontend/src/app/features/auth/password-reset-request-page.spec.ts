import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AuthApi } from '../../core/auth/auth-api';
import { PasswordResetRequestResult } from '../../core/auth/auth-models';
import { query, settle, typeInto } from '../../testing/dom';
import { PasswordResetRequestPage } from './password-reset-request-page';

describe('PasswordResetRequestPage', () => {
  let requestPasswordReset: ReturnType<
    typeof vi.fn<(email: string) => Promise<PasswordResetRequestResult>>
  >;
  let fixture: ComponentFixture<PasswordResetRequestPage>;
  let page: HTMLElement;

  async function setup(): Promise<void> {
    requestPasswordReset = vi.fn<(email: string) => Promise<PasswordResetRequestResult>>();
    TestBed.configureTestingModule({
      imports: [PasswordResetRequestPage],
      providers: [provideRouter([]), { provide: AuthApi, useValue: { requestPasswordReset } }],
    });
    fixture = TestBed.createComponent(PasswordResetRequestPage);
    page = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
  }

  async function submit(email = 'ann@example.com'): Promise<void> {
    typeInto(page, '#email', email);
    query(page, 'form').dispatchEvent(new Event('submit'));
    await settle(fixture);
  }

  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((el) => (el.textContent ?? '').trim());
  const button = () => query<HTMLButtonElement>(page, 'button[type="submit"]');

  it('shows a labelled email field and a way back to the sign-in', async () => {
    await setup();

    expect(page.querySelector('label[for="email"]')).not.toBeNull();
    expect(page.querySelector('input#email[type="email"]')).not.toBeNull();
    expect(query<HTMLAnchorElement>(page, 'a').getAttribute('href')).toBe('/login');
  });

  it('does not call the server for an invalid address', async () => {
    await setup();

    await submit('not-an-email');

    expect(requestPasswordReset).not.toHaveBeenCalled();
    expect(query(page, '#email-error').textContent).toContain('valid email');
  });

  it('sends the address and says a link was sent if an account exists', async () => {
    await setup();
    requestPasswordReset.mockResolvedValue({ kind: 'sent' });

    await submit('ann@example.com');

    expect(requestPasswordReset).toHaveBeenCalledExactlyOnceWith('ann@example.com');
    const notice = query(page, '[role="status"]').textContent ?? '';
    expect(notice).toContain('If an account exists for');
    expect(notice).toContain('ann@example.com');
    expect(page.querySelector('form')).toBeNull();
  });

  it('never claims that an account does or does not exist', async () => {
    await setup();
    requestPasswordReset.mockResolvedValue({ kind: 'sent' });

    await submit('nobody@example.com');

    const text = page.textContent ?? '';
    expect(text).not.toMatch(/no account|not found|unknown|does not exist/i);
  });

  it('asks to wait when the rate limit applies and keeps the form', async () => {
    await setup();
    requestPasswordReset.mockResolvedValue({ kind: 'rate_limited' });

    await submit();

    expect(alerts()).toEqual(['Too many requests. Please wait a minute and try again.']);
    expect(page.querySelector('form')).not.toBeNull();
    expect(button().disabled).toBe(false);
  });

  it('shows the message the server gives for an invalid address', async () => {
    await setup();
    requestPasswordReset.mockResolvedValue({
      kind: 'invalid',
      errors: [{ code: 'invalid', message: 'Enter a valid email address.', param: 'email' }],
    });

    await submit();

    expect(alerts()).toEqual(['Enter a valid email address.']);
  });

  it('shows a generic message when the request fails unexpectedly', async () => {
    await setup();
    requestPasswordReset.mockRejectedValue(new Error('network down'));

    await submit();

    expect(alerts()).toEqual(['Something went wrong. Please try again.']);
  });

  it('disables the button while the request is on its way', async () => {
    await setup();
    let finish!: (result: PasswordResetRequestResult) => void;
    requestPasswordReset.mockReturnValue(
      new Promise<PasswordResetRequestResult>((resolve) => (finish = resolve)),
    );

    await submit();
    expect(button().disabled).toBe(true);
    expect(button().textContent).toContain('Sending');

    finish({ kind: 'sent' });
    await settle(fixture);
    expect(page.querySelector('form')).toBeNull();
  });
});
