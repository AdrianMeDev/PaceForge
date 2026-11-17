import { existsSync, readFileSync } from 'node:fs';

// `ng test` runs in the folder of the project.
const manifest = JSON.parse(readFileSync('public/manifest.webmanifest', 'utf-8')) as {
  name: string;
  short_name: string;
  start_url: string;
  scope: string;
  display: string;
  theme_color: string;
  background_color: string;
  icons: { src: string; sizes: string; type: string; purpose?: string }[];
};
const page = readFileSync('src/index.html', 'utf-8');

describe('the web app manifest', () => {
  it('lets the browser install PaceForge as an app of its own', () => {
    expect(manifest.name).toBe('PaceForge');
    expect(manifest.short_name).toBe('PaceForge');
    expect(manifest.display).toBe('standalone');
    expect(manifest.start_url).toBe('/');
    expect(manifest.scope).toBe('/');
    expect(manifest.theme_color).toMatch(/^#[0-9a-f]{6}$/i);
    expect(manifest.background_color).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it('has icons of 192 and 512 px and one that can be masked', () => {
    const sizes = manifest.icons.map((icon) => icon.sizes);
    expect(sizes).toContain('192x192');
    expect(sizes).toContain('512x512');
    expect(manifest.icons.some((icon) => icon.purpose === 'maskable')).toBe(true);
  });

  it('names only icon files that exist', () => {
    for (const icon of manifest.icons) {
      expect(existsSync(`public/${icon.src}`), icon.src).toBe(true);
      expect(icon.type).toBe('image/png');
    }
    expect(existsSync('public/apple-touch-icon.png')).toBe(true);
  });

  it('is linked from the page, with the colours of the browser bar and the icon for iOS', () => {
    expect(page).toContain('<link rel="manifest" href="manifest.webmanifest"');
    expect(page).toContain('rel="apple-touch-icon" href="apple-touch-icon.png"');
    expect(page).toContain('name="theme-color"');
    expect(page).toContain('(prefers-color-scheme: dark)');
  });
});
