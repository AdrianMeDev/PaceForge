import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ICONS, ICON_NAMES, Icon, IconName } from './icon';

describe('Icon', () => {
  let fixture: ComponentFixture<Icon>;
  let host: HTMLElement;

  function show(name: string, label?: string) {
    TestBed.configureTestingModule({ imports: [Icon] });
    fixture = TestBed.createComponent(Icon);
    fixture.componentRef.setInput('name', name as IconName);
    if (label !== undefined) {
      fixture.componentRef.setInput('label', label);
    }
    host = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
  }

  it('has a drawing for every name, and no drawing without a name', () => {
    expect(Object.keys(ICONS).sort()).toEqual([...ICON_NAMES].sort());
    for (const name of ICON_NAMES) {
      expect(ICONS[name].length, name).toBeGreaterThan(0);
    }
  });

  it.each(ICON_NAMES.map((name) => [name]))('draws %s as one svg with its shapes', (name) => {
    show(name);

    const svg = host.querySelector('svg');
    expect(svg).toBeTruthy();
    expect(svg?.namespaceURI).toBe('http://www.w3.org/2000/svg');
    expect(svg?.getAttribute('viewBox')).toBe('0 0 24 24');
    const shapes = svg?.querySelectorAll('path, circle, rect, line') ?? [];
    expect(shapes.length).toBe(ICONS[name].length);
    for (const shape of Array.from(shapes)) {
      expect(shape.namespaceURI).toBe('http://www.w3.org/2000/svg');
    }
  });

  it('gives a circle its place', () => {
    show('target');

    expect(host.querySelector('circle')?.getAttribute('r')).toBe('10');
  });

  it('gives a path its d', () => {
    show('home');

    expect(host.querySelector('path')?.getAttribute('d')).toContain('M15 21v-8');
  });

  it('is decoration without a label: hidden from assistive technology', () => {
    show('check');

    expect(host.getAttribute('aria-hidden')).toBe('true');
    expect(host.hasAttribute('role')).toBe(false);
    expect(host.hasAttribute('aria-label')).toBe(false);
  });

  it('is an image with its name when it has a label', () => {
    show('check', 'Done');

    expect(host.getAttribute('role')).toBe('img');
    expect(host.getAttribute('aria-label')).toBe('Done');
    expect(host.hasAttribute('aria-hidden')).toBe(false);
  });

  it('takes the colour of its text and cannot be focused', () => {
    show('menu');

    const svg = host.querySelector('svg');
    expect(svg?.getAttribute('stroke')).toBe('currentColor');
    expect(svg?.getAttribute('focusable')).toBe('false');
  });

  it('draws nothing for a name it does not know', () => {
    show('nonsense');

    expect(host.querySelectorAll('path, circle, rect, line').length).toBe(0);
  });

  it('holds only plain numbers and path data in its drawings', () => {
    for (const [name, shapes] of Object.entries(ICONS)) {
      for (const shape of shapes) {
        for (const [key, value] of Object.entries(shape.attrs)) {
          expect(value, `${name} ${key}`).toMatch(/^[0-9a-zA-Z .,\-+]*$/);
        }
      }
    }
  });
});
