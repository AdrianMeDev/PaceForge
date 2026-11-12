import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { AuthApi } from '../../core/auth/auth-api';
import { PasswordResetKeyResult, PasswordResetResult } from '../../core/auth/auth-models';
import { query, settle, typeInto } from '../../testing/dom';
import { PasswordResetPage } from './password-reset-page';

const KEY = 'abc123-def456-ghi';
const NEW_PASSWORD = 'another-long-passphrase-42';

describe('PasswordResetPage', () => {
  let checkPasswordResetKey: ReturnType<
    typeof vi.fn<(key: string) => Promise<PasswordResetKeyResult>>
  >;
  let resetPassword: ReturnType<
    typeof vi.fn<(key: string, password: string) => Promise<PasswordResetResult>>
  >;
  let navigate: ReturnType<typeof vi.spyOn>;
  let fixture: ComponentFixture<PasswordResetPage>;
  let page: HTMLElement;

  /** `prepare` can queue different answers before the page asks for the first time. */
  async function setup(
    check: PasswordResetKeyResult = { kind: 'valid' },
    prepare?: (lookup: typeof checkPasswordResetKey) => void,
  ): Promise<void> {
    checkPasswordResetKey = vi.fn<(key: string) => Promise<PasswordResetKeyResult>>();
    checkPasswordResetKey.mockResolvedValue(check);
    prepare?.(checkPasswordResetKey);
    resetPassword = vi.fn<(key: string, password: string) => Promise<PasswordResetResult>>();
    TestBed.configureTestingModule({
      imports: [PasswordResetPage],
      providers: [
        provideRouter([]),
        { provide: AuthApi, useValue: { checkPasswordResetKey, resetPassword } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ key: KEY }) } },
        },
      ],
    });
    navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    fixture = TestBed.createComponent(PasswordResetPage);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  }

  async function submit(password = NEW_PASSWORD, confirm = password): Promise<void> {
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

  describe('checking the link', () => {
    it('says it is checking while the server has not answered', async () => {
      await setup({ kind: 'valid' }, (lookup) =>
        lookup.mockReturnValue(new Promise(() => undefined)),
      );

      expect(query(page, '[role="status"]').textContent).toContain('Checking your link');
      expect(page.querySelector('form')).toBeNull();
    });

    it('shows the form for a valid link, checked with the decoded route parameter', async () => {
      await setup();

      expect(checkPasswordResetKey).toHaveBeenCalledExactlyOnceWith(KEY);
      expect(page.querySelector('label[for="password"]')).not.toBeNull();
      expect(page.querySelector('label[for="passwordConfirm"]')).not.toBeNull();
      expect(query<HTMLInputElement>(page, '#password').autocomplete).toBe('new-password');
    });

    it('shows no form for an invalid or expired link and offers a new one', async () => {
      await setup({ kind: 'invalid', errors: [] });

      expect(alerts()).toEqual(['This reset link is invalid or has expired.']);
      expect(page.querySelector('form')).toBeNull();
      expect(query<HTMLAnchorElement>(page, 'a').getAttribute('href')).toBe(
        '/account/password/reset',
      );
    });

    it('asks to wait when the check hits the rate limit, and can try again', async () => {
      await setup({ kind: 'valid' }, (lookup) =>
        lookup
          .mockResolvedValueOnce({ kind: 'rate_limited' })
          .mockResolvedValueOnce({ kind: 'valid' }),
      );
      expect(alerts()).toEqual(['Too many attempts. Please wait a minute and try again.']);

      query<HTMLButtonElement>(page, 'button').click();
      await settle(fixture);

      expect(page.querySelector('form')).not.toBeNull();
      expect(alerts()).toEqual([]);
    });

    it('offers to try again when the link cannot be checked', async () => {
      await setup({ kind: 'valid' }, (lookup) =>
        lookup
          .mockRejectedValueOnce(new Error('network down'))
          .mockResolvedValueOnce({ kind: 'valid' }),
      );
      expect(alerts()).toEqual(['We could not check the link. Please try again.']);

      query<HTMLButtonElement>(page, 'button').click();
      await settle(fixture);

      expect(page.querySelector('form')).not.toBeNull();
    });
  });

  describe('choosing a password', () => {
    it('does not call the server for an incomplete form', async () => {
      await setup();

      await submit('', '');

      expect(resetPassword).not.toHaveBeenCalled();
      expect(fieldErrors()).toEqual(['Choose a password.', 'Repeat your password.']);
    });

    it('does not call the server when the passwords differ', async () => {
      await setup();

      await submit(NEW_PASSWORD, NEW_PASSWORD + 'x');

      expect(resetPassword).not.toHaveBeenCalled();
      expect(fieldErrors()).toEqual(['The passwords do not match.']);
    });

    it('sends key and password and then goes to the sign-in with a notice', async () => {
      await setup();
      resetPassword.mockResolvedValue({ kind: 'done' });

      await submit();

      expect(resetPassword).toHaveBeenCalledExactlyOnceWith(KEY, NEW_PASSWORD);
      expect(navigate).toHaveBeenCalledExactlyOnceWith(['/login'], {
        queryParams: { notice: 'password-reset' },
      });
    });

    it('shows the password rules of the server under the password field', async () => {
      await setup();
      resetPassword.mockResolvedValue({
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

      await submit('password');

      expect(fieldErrors()).toEqual(['This password is too common.', 'Too short.']);
      expect(navigate).not.toHaveBeenCalled();
      expect(page.querySelector('form')).not.toBeNull();
    });

    it('switches to the invalid-link message when the key stops working', async () => {
      await setup();
      resetPassword.mockResolvedValue({
        kind: 'invalid',
        errors: [{ code: 'invalid_password_reset', message: 'Expired.', param: 'key' }],
      });

      await submit();

      expect(alerts()).toEqual(['This reset link is invalid or has expired.']);
      expect(page.querySelector('form')).toBeNull();
    });

    it('asks to wait when the rate limit applies', async () => {
      await setup();
      resetPassword.mockResolvedValue({ kind: 'rate_limited' });

      await submit();

      expect(alerts()).toEqual(['Too many attempts. Please wait a minute and try again.']);
      expect(submitButton().disabled).toBe(false);
    });

    it('shows a generic message when saving fails unexpectedly', async () => {
      await setup();
      resetPassword.mockRejectedValue(new Error('boom'));

      await submit();

      expect(alerts()).toEqual(['Something went wrong. Please try again.']);
      expect(submitButton().disabled).toBe(false);
    });

    it('disables the button while the password is being saved', async () => {
      await setup();
      let finish!: (result: PasswordResetResult) => void;
      resetPassword.mockReturnValue(
        new Promise<PasswordResetResult>((resolve) => (finish = resolve)),
      );

      await submit();
      expect(submitButton().disabled).toBe(true);
      expect(submitButton().textContent).toContain('Saving');

      finish({ kind: 'done' });
      await settle(fixture);
      expect(navigate).toHaveBeenCalledTimes(1);
    });
  });
});
