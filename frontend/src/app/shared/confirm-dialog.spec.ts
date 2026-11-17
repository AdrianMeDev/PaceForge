import type { Mock } from 'vitest';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { query } from '../testing/dom';
import { ConfirmDialog } from './confirm-dialog';

describe('ConfirmDialog', () => {
  // jsdom has no modal dialog: this is what the browser does that the dialog relies on.
  beforeAll(() => {
    HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
      this.setAttribute('open', '');
    };
    HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
      if (this.hasAttribute('open')) {
        this.removeAttribute('open');
        this.dispatchEvent(new Event('close'));
      }
    };
  });

  let fixture: ComponentFixture<ConfirmDialog>;
  let confirmed: Mock<() => void>;

  function show(inputs: Record<string, unknown> = {}): HTMLElement {
    fixture = TestBed.createComponent(ConfirmDialog);
    fixture.componentRef.setInput('title', 'Discard this draft?');
    fixture.componentRef.setInput('message', 'It cannot be brought back.');
    for (const [name, value] of Object.entries(inputs)) {
      fixture.componentRef.setInput(name, value);
    }
    confirmed = vi.fn<() => void>();
    fixture.componentInstance.confirmed.subscribe(confirmed);
    fixture.detectChanges();
    return fixture.nativeElement;
  }

  const dialog = (page: HTMLElement) =>
    query<HTMLDialogElement>(page, '[data-testid="confirm-dialog"]');

  it('is closed until it is opened, and says what it asks', () => {
    const page = show();

    expect(dialog(page).open).toBe(false);
    fixture.componentInstance.open();
    expect(dialog(page).open).toBe(true);
    expect(query(page, 'h2').textContent).toBe('Discard this draft?');
    expect(query(page, '[data-testid="confirm-dialog-message"]').textContent).toBe(
      'It cannot be brought back.',
    );
    expect(dialog(page).getAttribute('aria-labelledby')).toBe('confirm-dialog-title');
  });

  it('confirms and closes', () => {
    const page = show({ confirmLabel: 'Discard draft' });
    fixture.componentInstance.open();

    const button = query<HTMLButtonElement>(page, '[data-testid="confirm-dialog-confirm"]');
    expect(button.textContent?.trim()).toBe('Discard draft');
    button.click();

    expect(confirmed).toHaveBeenCalledTimes(1);
    expect(dialog(page).open).toBe(false);
  });

  it('closes without confirming on "Cancel" and on a click on the backdrop', () => {
    const page = show();
    fixture.componentInstance.open();
    query<HTMLButtonElement>(page, '[data-testid="confirm-dialog-cancel"]').click();
    expect(dialog(page).open).toBe(false);

    fixture.componentInstance.open();
    dialog(page).click();
    expect(dialog(page).open).toBe(false);

    fixture.componentInstance.open();
    query(page, 'h2').click();
    expect(dialog(page).open).toBe(true);
    expect(confirmed).not.toHaveBeenCalled();
  });

  it('can be a danger button', () => {
    const page = show({ danger: true });

    const button = query(page, '[data-testid="confirm-dialog-confirm"]');
    expect(button.classList).toContain('btn-danger');
    expect(button.classList).not.toContain('btn-primary');
  });
});
