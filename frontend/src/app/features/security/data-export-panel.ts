import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { AuthApi } from '../../core/auth/auth-api';

const RATE_LIMIT = 'Too many attempts. Please wait a minute and try again.';
const SIGNED_OUT = 'You are signed out. Please sign in again to download your data.';
const FALLBACK = 'Something went wrong. Please try again.';

/** Lets the athlete download everything PaceForge stores about them as one JSON file. */
@Component({
  selector: 'app-data-export-panel',
  templateUrl: './data-export-panel.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DataExportPanel {
  private readonly api = inject(AuthApi);

  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);

  protected async download(): Promise<void> {
    if (this.busy()) {
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    try {
      const result = await this.api.exportAccountData();
      switch (result.kind) {
        case 'exported':
          this.save(result.file, result.filename);
          break;
        case 'forbidden':
          this.error.set(SIGNED_OUT);
          break;
        case 'rate_limited':
          this.error.set(RATE_LIMIT);
          break;
      }
    } catch {
      this.error.set(FALLBACK);
    } finally {
      this.busy.set(false);
    }
  }

  private save(file: Blob, filename: string): void {
    const url = URL.createObjectURL(file);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }
}
