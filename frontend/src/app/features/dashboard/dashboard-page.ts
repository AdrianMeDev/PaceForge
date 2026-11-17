import { Component } from '@angular/core';
import { PageHeader } from '../../shared/page-header';

/** Placeholder until the training overview exists. */
@Component({
  selector: 'app-dashboard-page',
  imports: [PageHeader],
  template: `<app-page-header
    title="Dashboard"
    subtitle="Your training overview will appear here."
  />`,
})
export class DashboardPage {}
