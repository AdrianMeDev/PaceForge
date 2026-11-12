import { Component, computed, input } from '@angular/core';
import { encode } from 'uqr';

/**
 * One SVG path for all dark modules of a QR matrix. Runs of neighbouring modules in a row are
 * merged into a single rectangle, which keeps the path short.
 */
export function matrixToPath(matrix: readonly (readonly boolean[])[]): string {
  const rectangles: string[] = [];
  matrix.forEach((row, y) => {
    let x = 0;
    while (x < row.length) {
      if (!row[x]) {
        x++;
        continue;
      }
      const start = x;
      while (x < row.length && row[x]) {
        x++;
      }
      const length = x - start;
      rectangles.push(`M${start} ${y}h${length}v1h-${length}z`);
    }
  });
  return rectangles.join('');
}

/**
 * A QR code drawn in the browser. The text never leaves the page: this matters for the
 * authenticator setup, whose URL contains the secret.
 *
 * Always black on white with a quiet zone, whatever the colour scheme: scanners need that
 * contrast. The picture is built from numbers only (no `innerHTML`, no external requests).
 */
@Component({
  selector: 'app-qr-code',
  template: `
    <svg
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      shape-rendering="crispEdges"
      [attr.viewBox]="viewBox()"
      [attr.aria-label]="label()"
    >
      <rect width="100%" height="100%" fill="#ffffff" />
      <path [attr.d]="path()" fill="#000000" />
    </svg>
  `,
  styles: `
    :host {
      display: block;
      width: 100%;
      max-width: 14rem;
    }

    svg {
      display: block;
      width: 100%;
      height: auto;
      border-radius: 4px;
    }
  `,
})
export class QrCode {
  /** The text to encode, e.g. an `otpauth://` URL. */
  readonly value = input.required<string>();
  /** What a screen reader says about the picture. */
  readonly label = input('QR code');
  /** Width of the empty quiet zone in modules; scanners want at least 2. */
  readonly border = input(2);

  private readonly qr = computed(() => encode(this.value(), { ecc: 'M', border: this.border() }));

  protected readonly viewBox = computed(() => `0 0 ${this.qr().size} ${this.qr().size}`);
  protected readonly path = computed(() => matrixToPath(this.qr().data));
}
