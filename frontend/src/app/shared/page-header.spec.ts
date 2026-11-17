import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { PageHeader } from './page-header';

@Component({
  imports: [PageHeader],
  template: `
    <app-page-header title="Week plan" subtitle="Draft, read and confirm.">
      <button type="button">Draft</button>
    </app-page-header>
  `,
})
class WithAction {}

@Component({ imports: [PageHeader], template: `<app-page-header title="Goals" />` })
class Alone {}

describe('PageHeader', () => {
  function render<T>(component: new () => T): HTMLElement {
    TestBed.configureTestingModule({ imports: [component as never] });
    const fixture = TestBed.createComponent(component);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('has the title as the one h1', () => {
    const page = render(Alone);

    expect(page.querySelectorAll('h1').length).toBe(1);
    expect(page.querySelector('h1')?.textContent?.trim()).toBe('Goals');
  });

  it('leaves out the subtitle when there is none', () => {
    expect(render(Alone).querySelector('[data-testid="subtitle"]')).toBeNull();
  });

  it('shows the subtitle as text under the title', () => {
    const page = render(WithAction);

    expect(page.querySelector('[data-testid="subtitle"]')?.textContent?.trim()).toBe(
      'Draft, read and confirm.',
    );
  });

  it('shows the action of the page next to the title', () => {
    const page = render(WithAction);

    expect(page.querySelector('[data-testid="actions"] button')?.textContent?.trim()).toBe('Draft');
  });

  it('keeps an empty place for the action out of the way', () => {
    const slot = render(Alone).querySelector('[data-testid="actions"]');

    expect(slot?.className).toContain('empty:hidden');
    expect(slot?.children.length).toBe(0);
  });

  it('does not read markup in the title or the subtitle', () => {
    TestBed.configureTestingModule({ imports: [PageHeader] });
    const fixture = TestBed.createComponent(PageHeader);
    fixture.componentRef.setInput('title', '<b>Plan</b>');
    fixture.componentRef.setInput('subtitle', '<i>x</i>');
    fixture.detectChanges();
    const page = fixture.nativeElement as HTMLElement;

    expect(page.querySelector('h1 b')).toBeNull();
    expect(page.querySelector('[data-testid="subtitle"] i')).toBeNull();
    expect(page.querySelector('h1')?.textContent).toContain('<b>Plan</b>');
  });
});
