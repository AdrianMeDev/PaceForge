import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { AuthApi } from '../../core/auth/auth-api';
import { SignupRequest, SignupResult } from '../../core/auth/auth-models';
import { query, settle, typeInto } from '../../testing/dom';
import { SignupPage } from './signup-page';

const PASSWORD = 'correct-horse-battery-9';

describe('SignupPage', () => {
  let signup: ReturnType<typeof vi.fn<(request: SignupRequest) => Promise<SignupResult>>>;
  let fixture: ComponentFixture<SignupPage>;
  let page: HTMLElement;

  async function setup(params: Record<string, string> = { invitation: 'tok-123' }): Promise<void> {
    signup = vi.fn<(request: SignupRequest) => Promise<SignupResult>>();
    TestBed.configureTestingModule({
      imports: [SignupPage],
      providers: [
        provideRouter([]),
        { provide: AuthApi, useValue: { signup } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap(params) } },
        },
      ],
    });
    fixture = TestBed.createComponent(SignupPage);
    page = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
  }

  async function submit(options: { email?: string; password?: string; confirm?: string } = {}) {
    const { email, password = PASSWORD, confirm = password } = options;
    if (email !== undefined) {
      typeInto(page, '#email', email);
    }
    typeInto(page, '#password', password);
    typeInto(page, '#passwordConfirm', confirm);
    query(page, 'form').dispatchEvent(new Event('submit'));
    await settle(fixture);
  }

  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((el) => (el.textContent ?? '').trim());
  const fieldErrors = () =>
    Array.from(page.querySelectorAll('.field-error')).map((el) => (el.textContent ?? '').trim());
  const submitButton = () => query<HTMLButtonElement>(page, 'button[type="submit"]');

  describe('without an invitation token', () => {
    const withoutToken: Record<string, string>[] = [{}, { invitation: '' }, { invitation: '   ' }];

    it.each(withoutToken)(
      'explains that registration needs an invitation and shows no form for %j',
      async (params) => {
        await setup(params);

        expect(page.textContent).toContain('by invitation only');
        expect(page.querySelector('form')).toBeNull();
        expect(page.querySelector('a[href="/login"]')).not.toBeNull();
      },
    );
  });

  describe('form', () => {
    it('shows labelled fields', async () => {
      await setup();

      for (const id of ['email', 'password', 'passwordConfirm']) {
        expect(page.querySelector(`label[for="${id}"]`)).not.toBeNull();
        expect(page.querySelector(`input#${id}`)).not.toBeNull();
      }
      expect(query<HTMLInputElement>(page, '#password').autocomplete).toBe('new-password');
    });

    it('prefills the email from the link and does not let it be edited', async () => {
      await setup({ invitation: 'tok-123', email: 'ann+run@example.com' });

      const email = query<HTMLInputElement>(page, '#email');
      expect(email.value).toBe('ann+run@example.com');
      expect(email.readOnly).toBe(true);
      expect(page.textContent).toContain('address your invitation was sent to');
    });

    it('lets the visitor type the email when the link has none', async () => {
      await setup();

      const email = query<HTMLInputElement>(page, '#email');
      expect(email.value).toBe('');
      expect(email.readOnly).toBe(false);
    });

    it('does not call the server for an incomplete form and says what is missing', async () => {
      await setup();

      await submit({ email: 'not-an-email', password: '', confirm: '' });

      expect(signup).not.toHaveBeenCalled();
      expect(fieldErrors()).toEqual([
        'Enter a valid email address.',
        'Choose a password.',
        'Repeat your password.',
      ]);
    });

    it('does not call the server when the passwords differ', async () => {
      await setup();

      await submit({ email: 'ann@example.com', password: PASSWORD, confirm: PASSWORD + 'x' });

      expect(signup).not.toHaveBeenCalled();
      expect(fieldErrors()).toEqual(['The passwords do not match.']);
    });
  });

  describe('submitting', () => {
    it('sends email, password and the invitation token and then asks to check the inbox', async () => {
      await setup({ invitation: 'tok-123', email: 'ann@example.com' });
      signup.mockResolvedValue({
        kind: 'pending',
        flows: [{ id: 'verify_email', is_pending: true }],
      });

      await submit();

      expect(signup).toHaveBeenCalledWith({
        email: 'ann@example.com',
        password: PASSWORD,
        invitationToken: 'tok-123',
      });
      expect(page.querySelector('form')).toBeNull();
      expect(query(page, '[role="status"]').textContent).toContain('ann@example.com');
      expect(query(page, '[role="status"]').textContent).toContain('confirmation link');
      expect(page.querySelector('a[href="/login"]')).not.toBeNull();
    });

    it('says the account can be used right away when no verification is needed', async () => {
      await setup();
      signup.mockResolvedValue({ kind: 'authenticated' });

      await submit({ email: 'ann@example.com' });

      expect(query(page, '[role="status"]').textContent).toContain('You can sign in now');
    });

    it('explains an invitation that does not fit and keeps the form', async () => {
      await setup();
      signup.mockResolvedValue({
        kind: 'invalid',
        errors: [{ code: 'invalid_invitation', message: 'raw', param: 'invitation_token' }],
      });

      await submit({ email: 'ann@example.com' });

      expect(alerts()).toEqual([
        'This invitation is invalid, has expired or was issued for a different email address.',
      ]);
      expect(page.querySelector('form')).not.toBeNull();
      expect(submitButton().disabled).toBe(false);
    });

    it('shows password rule violations under the password field', async () => {
      await setup();
      signup.mockResolvedValue({
        kind: 'invalid',
        errors: [
          {
            code: 'password_too_common',
            message: 'This password is too common.',
            param: 'password',
          },
          { code: 'password_too_short', message: 'Too short.', param: 'password' },
        ],
      });

      await submit({ email: 'ann@example.com' });

      expect(fieldErrors()).toEqual(['This password is too common.', 'Too short.']);
      expect(alerts()).toEqual([]);
    });

    it('shows other server messages as alerts', async () => {
      await setup();
      signup.mockResolvedValue({
        kind: 'invalid',
        errors: [{ code: 'email_taken', message: 'Pick another address.', param: 'email' }],
      });

      await submit({ email: 'ann@example.com' });

      expect(alerts()).toEqual(['Pick another address.']);
    });

    it('falls back to a generic message for an invalid reply without errors', async () => {
      await setup();
      signup.mockResolvedValue({ kind: 'invalid', errors: [] });

      await submit({ email: 'ann@example.com' });

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    });

    it('reports closed registration', async () => {
      await setup();
      signup.mockResolvedValue({ kind: 'closed' });

      await submit({ email: 'ann@example.com' });

      expect(alerts()).toEqual(['Registration is closed on this server.']);
    });

    it('reports the rate limit', async () => {
      await setup();
      signup.mockResolvedValue({ kind: 'rate_limited' });

      await submit({ email: 'ann@example.com' });

      expect(alerts()).toEqual(['Too many attempts. Please wait a minute and try again.']);
    });

    it('shows a generic message when the request fails unexpectedly', async () => {
      await setup();
      signup.mockRejectedValue(new Error('network down'));

      await submit({ email: 'ann@example.com' });

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(submitButton().disabled).toBe(false);
    });

    it('disables the button while the account is being created', async () => {
      await setup();
      let finish!: (result: SignupResult) => void;
      signup.mockReturnValue(new Promise<SignupResult>((resolve) => (finish = resolve)));

      await submit({ email: 'ann@example.com' });
      expect(submitButton().disabled).toBe(true);
      expect(submitButton().textContent).toContain('Creating account');

      finish({ kind: 'closed' });
      await settle(fixture);
      expect(submitButton().disabled).toBe(false);
    });
  });
});
