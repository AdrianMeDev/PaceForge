import { ComponentFixture, TestBed } from '@angular/core/testing';
import { encode } from 'uqr';
import { query } from '../testing/dom';
import { QrCode, matrixToPath } from './qr-code';

const URL = 'otpauth://totp/ada%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=PaceForge';

/** The cells a path of `M x y h n v1 h-n z` rectangles paints, as "x,y". */
function paintedCells(path: string): Set<string> {
  const cells = new Set<string>();
  for (const [, x, y, length] of path.matchAll(/M(\d+) (\d+)h(\d+)v1h-\d+z/g)) {
    for (let i = 0; i < Number(length); i++) {
      cells.add(`${Number(x) + i},${y}`);
    }
  }
  return cells;
}

function darkCells(matrix: boolean[][]): Set<string> {
  const cells = new Set<string>();
  matrix.forEach((row, y) => row.forEach((dark, x) => dark && cells.add(`${x},${y}`)));
  return cells;
}

describe('matrixToPath', () => {
  it('draws one unit square per isolated dark module', () => {
    expect(
      matrixToPath([
        [true, false],
        [false, true],
      ]),
    ).toBe('M0 0h1v1h-1zM1 1h1v1h-1z');
  });

  it('merges neighbouring dark modules of a row into one rectangle', () => {
    expect(matrixToPath([[true, true, false, true]])).toBe('M0 0h2v1h-2zM3 0h1v1h-1z');
  });

  it('keeps the row of each rectangle', () => {
    expect(matrixToPath([[false], [false], [true]])).toBe('M0 2h1v1h-1z');
  });

  it('is empty for an empty or all-light matrix', () => {
    expect(matrixToPath([])).toBe('');
    expect(matrixToPath([[false, false]])).toBe('');
  });
});

describe('QrCode', () => {
  let fixture: ComponentFixture<QrCode>;
  let host: HTMLElement;

  async function render(value: string, inputs: Record<string, unknown> = {}): Promise<void> {
    TestBed.configureTestingModule({ imports: [QrCode] });
    fixture = TestBed.createComponent(QrCode);
    fixture.componentRef.setInput('value', value);
    for (const [name, inputValue] of Object.entries(inputs)) {
      fixture.componentRef.setInput(name, inputValue);
    }
    host = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
  }

  const svg = () => query<SVGElement>(host, 'svg');
  const pathOf = () => query<SVGPathElement>(host, 'path').getAttribute('d') ?? '';
  const sizeOf = () => Number(svg().getAttribute('viewBox')?.split(' ')[2]);

  it('paints exactly the dark modules of the matrix that uqr encodes', async () => {
    await render(URL);

    const expected = encode(URL, { ecc: 'M', border: 2 });
    expect(svg().getAttribute('viewBox')).toBe(`0 0 ${expected.size} ${expected.size}`);
    expect(paintedCells(pathOf())).toEqual(darkCells(expected.data));
  });

  it('leaves a quiet zone: nothing is painted in the border', async () => {
    await render(URL, { border: 3 });

    const size = sizeOf();
    for (const cell of paintedCells(pathOf())) {
      const [x, y] = cell.split(',').map(Number);
      expect(x).toBeGreaterThanOrEqual(3);
      expect(y).toBeGreaterThanOrEqual(3);
      expect(x).toBeLessThan(size - 3);
      expect(y).toBeLessThan(size - 3);
    }
  });

  it('makes the picture two modules wider per extra module of border on each side', async () => {
    await render(URL, { border: 1 });
    const narrow = sizeOf();

    fixture.componentRef.setInput('border', 3);
    await fixture.whenStable();

    expect(sizeOf()).toBe(narrow + 4);
  });

  it('draws different input differently and the same input identically', async () => {
    await render(URL);
    const first = pathOf();

    fixture.componentRef.setInput('value', URL.replace('JBSWY3DP', 'ZZZZZZZZ'));
    await fixture.whenStable();
    const other = pathOf();
    fixture.componentRef.setInput('value', URL);
    await fixture.whenStable();

    expect(other).not.toBe(first);
    expect(pathOf()).toBe(first);
  });

  it('is black on white whatever the colour scheme', async () => {
    await render(URL);

    expect(query(host, 'rect').getAttribute('fill')).toBe('#ffffff');
    expect(query(host, 'path').getAttribute('fill')).toBe('#000000');
  });

  it('is announced as an image with a label', async () => {
    await render(URL);
    expect(svg().getAttribute('role')).toBe('img');
    expect(svg().getAttribute('aria-label')).toBe('QR code');

    fixture.componentRef.setInput('label', 'QR code for your authenticator app');
    await fixture.whenStable();

    expect(svg().getAttribute('aria-label')).toBe('QR code for your authenticator app');
  });

  it('contains nothing that could load or run anything from elsewhere', async () => {
    await render(URL);

    const markup = host.innerHTML;
    expect(markup).not.toMatch(/\b(href|src|xlink:href)=/i);
    expect(host.querySelector('image, foreignObject, script, use, a')).toBeNull();
  });

  it('does not put the encoded text into the document', async () => {
    await render(URL);

    expect(host.innerHTML).not.toContain('JBSWY3DP');
  });
});
