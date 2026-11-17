import { ComponentFixture, TestBed } from '@angular/core/testing';
import { query } from '../testing/dom';
import { ChipVersion, VersionChips } from './version-chips';

const VERSIONS: ChipVersion[] = [
  { id: 'b', version: 2, status: 'draft', created_at: '2026-11-17T09:30:00Z' },
  { id: 'a', version: 1, status: 'superseded', created_at: '2026-11-10T09:30:00Z' },
];

describe('VersionChips', () => {
  let fixture: ComponentFixture<VersionChips>;
  let opened: ReturnType<typeof vi.fn<(id: string) => void>>;

  function show(inputs: Record<string, unknown> = {}): HTMLElement {
    fixture = TestBed.createComponent(VersionChips);
    fixture.componentRef.setInput('versions', VERSIONS);
    for (const [name, value] of Object.entries(inputs)) {
      fixture.componentRef.setInput(name, value);
    }
    opened = vi.fn<(id: string) => void>();
    fixture.componentInstance.opened.subscribe(opened);
    fixture.detectChanges();
    return fixture.nativeElement;
  }

  const chip = (page: HTMLElement, version: number) =>
    query<HTMLButtonElement>(page, `[data-testid="version-${version}"]`);

  it('shows a short text and keeps the date for screen readers', () => {
    const page = show({ label: 'Versions of this week' });

    expect(chip(page, 2).textContent?.replace(/\s+/g, ' ').trim()).toBe('v2 · Draft');
    expect(chip(page, 2).getAttribute('aria-label')).toMatch(
      /^Version 2, Draft, [A-Z][a-z]{2} \d{1,2}, \d{2}:\d{2}$/,
    );
    expect(query(page, 'ul').getAttribute('aria-label')).toBe('Versions of this week');
  });

  it('marks the version that is shown', () => {
    const page = show({ selected: 'a' });

    expect(chip(page, 1).getAttribute('aria-current')).toBe('true');
    expect(chip(page, 2).getAttribute('aria-current')).toBeNull();
  });

  it('says which version was chosen', () => {
    const page = show();

    chip(page, 1).click();

    expect(opened).toHaveBeenCalledExactlyOnceWith('a');
  });

  it('can be switched off', () => {
    const page = show({ disabled: true });

    expect(chip(page, 1).disabled).toBe(true);
  });
});
