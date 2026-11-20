import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AuthApi } from '../../core/auth/auth-api';
import { AccountExportResult } from '../../core/auth/auth-models';
import { query, settle } from '../../testing/dom';
import { DataExportPanel } from './data-export-panel';

const FILE = new Blob(['{}'], { type: 'application/json' });

describe('DataExportPanel', () => {
  let api: { exportAccountData: ReturnType<typeof vi.fn<() => Promise<AccountExportResult>>> };
  let fixture: ComponentFixture<DataExportPanel>;
  let page: HTMLElement;
  let createUrl: ReturnType<typeof vi.fn>;
  let revokeUrl: ReturnType<typeof vi.fn>;
  let clicked: HTMLAnchorElement[];

  beforeEach(async () => {
    api = { exportAccountData: vi.fn<() => Promise<AccountExportResult>>() };
    createUrl = vi.fn().mockReturnValue('blob:fake');
    revokeUrl = vi.fn();
    Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: revokeUrl });
    clicked = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push(this);
    });
    TestBed.configureTestingModule({
      imports: [DataExportPanel],
      providers: [{ provide: AuthApi, useValue: api }],
    });
    fixture = TestBed.createComponent(DataExportPanel);
    page = fixture.nativeElement as HTMLElement;
    await settle(fixture);
  });

  const button = () => query<HTMLButtonElement>(page, 'button');
  const alerts = () =>
    Array.from(page.querySelectorAll('[role="alert"]')).map((el) => (el.textContent ?? '').trim());

  async function download(): Promise<void> {
    button().click();
    await settle(fixture);
  }

  it('explains what the file contains and what it leaves out', () => {
    const text = page.textContent ?? '';

    expect(query(page, 'h2').textContent).toBe('Your data');
    expect(text).toContain('chat history');
    expect(text).toContain('does not contain your password');
  });

  it('saves the file under the name the server suggests', async () => {
    api.exportAccountData.mockResolvedValue({
      kind: 'exported',
      file: FILE,
      filename: 'paceforge-export.json',
    });

    await download();

    expect(createUrl).toHaveBeenCalledExactlyOnceWith(FILE);
    expect(clicked).toHaveLength(1);
    expect(clicked[0].download).toBe('paceforge-export.json');
    expect(clicked[0].href).toBe('blob:fake');
    expect(revokeUrl).toHaveBeenCalledExactlyOnceWith('blob:fake');
    expect(alerts()).toEqual([]);
  });

  it('is busy while the file is prepared and ignores a second click', async () => {
    let finish!: (result: AccountExportResult) => void;
    api.exportAccountData.mockReturnValue(
      new Promise<AccountExportResult>((resolve) => (finish = resolve)),
    );

    await download();
    expect(button().disabled).toBe(true);
    expect(button().textContent).toContain('Preparing');
    await download();

    expect(api.exportAccountData).toHaveBeenCalledTimes(1);
    finish({ kind: 'forbidden' });
    await settle(fixture);
    expect(button().disabled).toBe(false);
  });

  it('asks to wait when the rate limit applies', async () => {
    api.exportAccountData.mockResolvedValue({ kind: 'rate_limited' });

    await download();

    expect(alerts()).toEqual(['Too many attempts. Please wait a minute and try again.']);
    expect(clicked).toHaveLength(0);
  });

  it('says so when the user is signed out', async () => {
    api.exportAccountData.mockResolvedValue({ kind: 'forbidden' });

    await download();

    expect(alerts()).toEqual(['You are signed out. Please sign in again to download your data.']);
  });

  it('shows a generic message when the download fails, then allows a new try', async () => {
    api.exportAccountData.mockRejectedValueOnce(new Error('boom'));

    await download();

    expect(alerts()).toEqual(['Something went wrong. Please try again.']);
    expect(button().disabled).toBe(false);
    api.exportAccountData.mockResolvedValue({ kind: 'rate_limited' });
    await download();
    expect(alerts()).toEqual(['Too many attempts. Please wait a minute and try again.']);
  });
});
