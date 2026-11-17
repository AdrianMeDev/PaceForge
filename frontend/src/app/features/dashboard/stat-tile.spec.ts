import { ComponentFixture, TestBed } from '@angular/core/testing';
import { query } from '../../testing/dom';
import { StatTile } from './stat-tile';

describe('StatTile', () => {
  let fixture: ComponentFixture<StatTile>;

  function show(inputs: Record<string, unknown>): HTMLElement {
    fixture = TestBed.createComponent(StatTile);
    for (const [name, value] of Object.entries(inputs)) {
      fixture.componentRef.setInput(name, value);
    }
    fixture.detectChanges();
    return fixture.nativeElement;
  }

  it('shows the label, the value and the detail', () => {
    const tile = show({ label: 'Minutes', value: '1 h 30 min', detail: 'of 4 h planned' });

    expect(query(tile, '[data-testid=label]').textContent).toBe('Minutes');
    expect(query(tile, '[data-testid=value]').textContent).toBe('1 h 30 min');
    expect(query(tile, '[data-testid=detail]').textContent).toBe('of 4 h planned');
  });

  it('has neither a detail nor a bar unless it is given one', () => {
    const tile = show({ label: 'Average RPE', value: '–' });

    expect(tile.querySelector('[data-testid=detail]')).toBeNull();
    expect(tile.querySelector('[role=progressbar]')).toBeNull();
  });

  it('shows how far along it is, named by its label', () => {
    const tile = show({ label: 'Minutes', value: '30', progress: 37.5 });

    const bar = query(tile, '[role=progressbar]');
    expect(bar.getAttribute('aria-valuenow')).toBe('38');
    expect(bar.getAttribute('aria-label')).toBe('Minutes');
    expect(query(bar, 'div').style.width).toBe('38%');
  });

  it.each([
    [150, '100'],
    [-5, '0'],
    [0, '0'],
  ])('keeps a bar of %s percent between empty and full', (progress, shown) => {
    const tile = show({ label: 'Minutes', value: '30', progress });

    expect(query(tile, '[role=progressbar]').getAttribute('aria-valuenow')).toBe(shown);
  });
});
