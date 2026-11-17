import { Component, computed, input } from '@angular/core';

/*
 * The icons are drawings of Lucide (https://lucide.dev), copied from lucide-static 1.73.0 on a
 * 24 x 24 grid, drawn with a 2 px stroke. They are data in this file, not a dependency. Some names
 * differ from Lucide's: `home` is `house`, `running` is `footprints`, `more` is `ellipsis` and
 * `alert-triangle` is `triangle-alert`. Lucide's licence, and that of the Feather icons some of
 * them are derived from (calendar, check, chevron-right, clock, link, log-out, monitor, moon,
 * target, upload, x, alert-triangle), follow as they are:
 *
 * ISC License
 *
 * Copyright (c) 2026 Lucide Icons and Contributors
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted, provided that the above
 * copyright notice and this permission notice appear in all copies.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 * WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 * ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 * WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 * ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 * OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 * The MIT License (MIT) (for the icons listed above)
 *
 * Copyright (c) 2013-present Cole Bemis
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

export interface Shape {
  tag: 'path' | 'circle' | 'rect' | 'line';
  attrs: Record<string, string>;
}

export const ICONS: Record<string, readonly Shape[]> = {
  home: [
    { tag: 'path', attrs: { d: 'M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8' } },
    {
      tag: 'path',
      attrs: {
        d: 'M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
      },
    },
  ],
  calendar: [
    { tag: 'path', attrs: { d: 'M8 2v3' } },
    { tag: 'path', attrs: { d: 'M16 2v3' } },
    { tag: 'rect', attrs: { x: '3', y: '3', width: '18', height: '18', rx: '2' } },
    { tag: 'path', attrs: { d: 'M3 9h18' } },
  ],
  'calendar-check': [
    { tag: 'path', attrs: { d: 'M8 2v3' } },
    { tag: 'path', attrs: { d: 'M16 2v3' } },
    { tag: 'rect', attrs: { x: '3', y: '3', width: '18', height: '18', rx: '2' } },
    { tag: 'path', attrs: { d: 'M3 9h18' } },
    { tag: 'path', attrs: { d: 'm9 15 2 2 4-4' } },
  ],
  activity: [
    {
      tag: 'path',
      attrs: {
        d: 'M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2',
      },
    },
  ],
  target: [
    { tag: 'circle', attrs: { cx: '12', cy: '12', r: '10' } },
    { tag: 'circle', attrs: { cx: '12', cy: '12', r: '6' } },
    { tag: 'circle', attrs: { cx: '12', cy: '12', r: '2' } },
  ],
  flag: [
    {
      tag: 'path',
      attrs: {
        d: 'M4 22V4a1 1 0 0 1 .4-.8A6 6 0 0 1 8 2c3 0 5 2 7.333 2q2 0 3.067-.8A1 1 0 0 1 20 4v10a1 1 0 0 1-.4.8A6 6 0 0 1 16 16c-3 0-5-2-8-2a6 6 0 0 0-4 1.528',
      },
    },
  ],
  clock: [
    { tag: 'circle', attrs: { cx: '12', cy: '12', r: '10' } },
    { tag: 'path', attrs: { d: 'M12 6v6l4 2' } },
  ],
  settings: [
    {
      tag: 'path',
      attrs: {
        d: 'M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915',
      },
    },
    { tag: 'circle', attrs: { cx: '12', cy: '12', r: '3' } },
  ],
  user: [
    { tag: 'path', attrs: { d: 'M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2' } },
    { tag: 'circle', attrs: { cx: '12', cy: '7', r: '4' } },
  ],
  link: [
    { tag: 'path', attrs: { d: 'M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71' } },
    { tag: 'path', attrs: { d: 'M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71' } },
  ],
  shield: [
    {
      tag: 'path',
      attrs: {
        d: 'M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z',
      },
    },
  ],
  upload: [
    { tag: 'path', attrs: { d: 'M12 3v12' } },
    { tag: 'path', attrs: { d: 'm17 8-5-5-5 5' } },
    { tag: 'path', attrs: { d: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4' } },
  ],
  check: [{ tag: 'path', attrs: { d: 'M20 6 9 17l-5-5' } }],
  'alert-triangle': [
    {
      tag: 'path',
      attrs: { d: 'm21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3' },
    },
    { tag: 'path', attrs: { d: 'M12 9v4' } },
    { tag: 'path', attrs: { d: 'M12 17h.01' } },
  ],
  menu: [
    { tag: 'path', attrs: { d: 'M4 5h16' } },
    { tag: 'path', attrs: { d: 'M4 12h16' } },
    { tag: 'path', attrs: { d: 'M4 19h16' } },
  ],
  x: [
    { tag: 'path', attrs: { d: 'M18 6 6 18' } },
    { tag: 'path', attrs: { d: 'm6 6 12 12' } },
  ],
  'chevron-right': [{ tag: 'path', attrs: { d: 'm9 18 6-6-6-6' } }],
  sun: [
    { tag: 'circle', attrs: { cx: '12', cy: '12', r: '4' } },
    { tag: 'path', attrs: { d: 'M12 2v2' } },
    { tag: 'path', attrs: { d: 'M12 20v2' } },
    { tag: 'path', attrs: { d: 'm4.93 4.93 1.41 1.41' } },
    { tag: 'path', attrs: { d: 'm17.66 17.66 1.41 1.41' } },
    { tag: 'path', attrs: { d: 'M2 12h2' } },
    { tag: 'path', attrs: { d: 'M20 12h2' } },
    { tag: 'path', attrs: { d: 'm6.34 17.66-1.41 1.41' } },
    { tag: 'path', attrs: { d: 'm19.07 4.93-1.41 1.41' } },
  ],
  moon: [
    {
      tag: 'path',
      attrs: {
        d: 'M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401',
      },
    },
  ],
  monitor: [
    { tag: 'rect', attrs: { width: '20', height: '14', x: '2', y: '3', rx: '2' } },
    { tag: 'line', attrs: { x1: '8', x2: '16', y1: '21', y2: '21' } },
    { tag: 'line', attrs: { x1: '12', x2: '12', y1: '17', y2: '21' } },
  ],
  running: [
    {
      tag: 'path',
      attrs: {
        d: 'M4 16v-2.38C4 11.5 2.97 10.5 3 8c.03-2.72 1.49-6 4.5-6C9.37 2 10 3.8 10 5.5c0 3.11-2 5.66-2 8.68V16a2 2 0 1 1-4 0Z',
      },
    },
    {
      tag: 'path',
      attrs: {
        d: 'M20 20v-2.38c0-2.12 1.03-3.12 1-5.62-.03-2.72-1.49-6-4.5-6C14.63 6 14 7.8 14 9.5c0 3.11 2 5.66 2 8.68V20a2 2 0 1 0 4 0Z',
      },
    },
    { tag: 'path', attrs: { d: 'M16 17h4' } },
    { tag: 'path', attrs: { d: 'M4 13h4' } },
  ],
  bike: [
    { tag: 'circle', attrs: { cx: '18.5', cy: '17.5', r: '3.5' } },
    { tag: 'circle', attrs: { cx: '5.5', cy: '17.5', r: '3.5' } },
    { tag: 'circle', attrs: { cx: '15', cy: '5', r: '1' } },
    { tag: 'path', attrs: { d: 'M12 17.5V14l-3-3 4-3 2 3h2' } },
  ],
  waves: [
    { tag: 'path', attrs: { d: 'M2 12q2.5 2 5 0t5 0 5 0 5 0' } },
    { tag: 'path', attrs: { d: 'M2 19q2.5 2 5 0t5 0 5 0 5 0' } },
    { tag: 'path', attrs: { d: 'M2 5q2.5 2 5 0t5 0 5 0 5 0' } },
  ],
  dumbbell: [
    {
      tag: 'path',
      attrs: {
        d: 'M17.596 12.768a2 2 0 1 0 2.829-2.829l-1.768-1.767a2 2 0 0 0 2.828-2.829l-2.828-2.828a2 2 0 0 0-2.829 2.828l-1.767-1.768a2 2 0 1 0-2.829 2.829z',
      },
    },
    { tag: 'path', attrs: { d: 'm2.5 21.5 1.4-1.4' } },
    { tag: 'path', attrs: { d: 'm20.1 3.9 1.4-1.4' } },
    {
      tag: 'path',
      attrs: {
        d: 'M5.343 21.485a2 2 0 1 0 2.829-2.828l1.767 1.768a2 2 0 1 0 2.829-2.829l-6.364-6.364a2 2 0 1 0-2.829 2.829l1.768 1.767a2 2 0 0 0-2.828 2.829z',
      },
    },
    { tag: 'path', attrs: { d: 'm9.6 14.4 4.8-4.8' } },
  ],
  more: [
    { tag: 'circle', attrs: { cx: '12', cy: '12', r: '1' } },
    { tag: 'circle', attrs: { cx: '19', cy: '12', r: '1' } },
    { tag: 'circle', attrs: { cx: '5', cy: '12', r: '1' } },
  ],
  'log-out': [
    { tag: 'path', attrs: { d: 'm16 17 5-5-5-5' } },
    { tag: 'path', attrs: { d: 'M21 12H9' } },
    { tag: 'path', attrs: { d: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4' } },
  ],
  trophy: [
    { tag: 'path', attrs: { d: 'M10 14.66V17a1 1 0 0 1-1 1 2 2 0 0 0-2 2v2' } },
    { tag: 'path', attrs: { d: 'M14 14.66V17a1 1 0 0 0 1 1 2 2 0 0 1 2 2v2' } },
    { tag: 'path', attrs: { d: 'M17.916 10H19.5A2.5 2.5 0 0 0 22 7.5V5a1 1 0 0 0-1-1h-3' } },
    { tag: 'path', attrs: { d: 'M4 22h16' } },
    { tag: 'path', attrs: { d: 'M6 9a6 6 0 0 0 12 0V3a1 1 0 0 0-1-1H7a1 1 0 0 0-1 1z' } },
    { tag: 'path', attrs: { d: 'M6.084 10H4.5A2.5 2.5 0 0 1 2 7.5V5a1 1 0 0 1 1-1h3' } },
  ],
};

export const ICON_NAMES = [
  'home',
  'calendar',
  'calendar-check',
  'activity',
  'target',
  'flag',
  'clock',
  'settings',
  'user',
  'link',
  'shield',
  'upload',
  'check',
  'alert-triangle',
  'menu',
  'x',
  'chevron-right',
  'sun',
  'moon',
  'monitor',
  'running',
  'bike',
  'waves',
  'dumbbell',
  'more',
  'log-out',
  'trophy',
] as const;

export type IconName = (typeof ICON_NAMES)[number];

/**
 * One icon. It takes the colour of the text around it and the size of its font, so it follows
 * buttons, links and headings without any setting. Without a `label` it is decoration and hidden
 * from assistive technology (put the meaning in the text next to it); with one it is an image with
 * that name. The drawings are built as elements, never as markup from a string.
 */
@Component({
  selector: 'app-icon',
  host: {
    '[attr.role]': "label() ? 'img' : null",
    '[attr.aria-label]': 'label() || null',
    '[attr.aria-hidden]': "label() ? null : 'true'",
    style:
      'display: inline-flex; width: 1.25em; height: 1.25em; flex: none; vertical-align: -0.2em',
  },
  template: `<svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    width="100%"
    height="100%"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    focusable="false"
  >
    @for (shape of shapes(); track $index) {
      @switch (shape.tag) {
        @case ('path') {
          <svg:path [attr.d]="shape.attrs['d']" />
        }
        @case ('circle') {
          <svg:circle
            [attr.cx]="shape.attrs['cx']"
            [attr.cy]="shape.attrs['cy']"
            [attr.r]="shape.attrs['r']"
          />
        }
        @case ('rect') {
          <svg:rect
            [attr.x]="shape.attrs['x']"
            [attr.y]="shape.attrs['y']"
            [attr.width]="shape.attrs['width']"
            [attr.height]="shape.attrs['height']"
            [attr.rx]="shape.attrs['rx']"
            [attr.ry]="shape.attrs['ry']"
          />
        }
        @case ('line') {
          <svg:line
            [attr.x1]="shape.attrs['x1']"
            [attr.y1]="shape.attrs['y1']"
            [attr.x2]="shape.attrs['x2']"
            [attr.y2]="shape.attrs['y2']"
          />
        }
      }
    }
  </svg>`,
})
export class Icon {
  readonly name = input.required<IconName>();
  readonly label = input('');

  protected readonly shapes = computed(() => ICONS[this.name()] ?? []);
}
