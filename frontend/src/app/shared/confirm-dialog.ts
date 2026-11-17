import { Component, ElementRef, effect, input, output, viewChild } from '@angular/core';

/**
 * A question before something that cannot be taken back: a title, what will happen and two buttons.
 * It is a native modal `<dialog>`: the browser keeps the focus inside, closes it on Escape, makes
 * the page behind inert and puts the focus back on the button that opened it. The page calls
 * `open()` and listens for `confirmed`; leaving the dialog any other way asks nothing of it.
 */
@Component({
  selector: 'app-confirm-dialog',
  template: `
    <dialog
      #dialog
      class="m-auto w-[min(90vw,26rem)] rounded-lg border border-border bg-surface p-5 text-fg shadow-card backdrop:bg-black/50"
      aria-labelledby="confirm-dialog-title"
      data-testid="confirm-dialog"
    >
      <h2 id="confirm-dialog-title" class="m-0 mb-2 text-lg font-semibold">{{ title() }}</h2>
      <p class="m-0 mb-5 text-muted" data-testid="confirm-dialog-message">{{ message() }}</p>
      <div class="flex flex-wrap justify-end gap-2">
        <button
          type="button"
          class="btn btn-secondary"
          data-testid="confirm-dialog-cancel"
          (click)="close()"
        >
          {{ cancelLabel() }}
        </button>
        <button
          type="button"
          class="btn"
          [class.btn-danger]="danger()"
          [class.btn-primary]="!danger()"
          data-testid="confirm-dialog-confirm"
          (click)="confirm()"
        >
          {{ confirmLabel() }}
        </button>
      </div>
    </dialog>
  `,
})
export class ConfirmDialog {
  readonly title = input.required<string>();
  readonly message = input.required<string>();
  readonly confirmLabel = input('Confirm');
  readonly cancelLabel = input('Cancel');
  readonly danger = input(false);

  readonly confirmed = output<void>();

  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  constructor() {
    // A click on the dialog itself, not on what is in it, is a click on the backdrop. (Escape is
    // the way for the keyboard, so this is no template event.)
    effect((onCleanup) => {
      const dialog = this.dialog().nativeElement;
      const onClick = (event: MouseEvent): void => {
        if (event.target === dialog) {
          this.close();
        }
      };
      dialog.addEventListener('click', onClick);
      onCleanup(() => dialog.removeEventListener('click', onClick));
    });
  }

  open(): void {
    const dialog = this.dialog().nativeElement;
    if (!dialog.open) {
      dialog.showModal();
    }
  }

  close(): void {
    const dialog = this.dialog().nativeElement;
    if (dialog.open) {
      dialog.close();
    }
  }

  protected confirm(): void {
    this.close();
    this.confirmed.emit();
  }
}
