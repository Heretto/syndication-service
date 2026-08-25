import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-status-badge',
  imports: [CommonModule, MatIconModule],
  template: `
    <span class="badge" [class]="'badge-' + normalizedStatus">
      <mat-icon aria-hidden="true">{{ icon }}</mat-icon>
      {{ label }}
    </span>
  `,
  styles: [`
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      border-radius: 3px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      white-space: nowrap;
    }
    .badge mat-icon { font-size: 13px; width: 13px; height: 13px; }
    .badge-success { background: rgba(0,166,80,0.1); color: #006b34; }
    .badge-running { background: rgba(0,82,204,0.1); color: #0052cc; }
    .badge-error   { background: rgba(222,53,11,0.1); color: #b22a09; }
    .badge-warning { background: rgba(255,152,0,0.12); color: #e65100; }
    .badge-pending { background: rgba(151,160,175,0.15); color: #5e6e82; }
    .badge-skipped { background: rgba(151,160,175,0.15); color: #5e6e82; }
  `],
})
export class StatusBadgeComponent {
  @Input() status = '';

  get normalizedStatus(): string {
    const s = (this.status || '').toLowerCase();
    if (s === 'success' || s === 'completed') return 'success';
    if (s === 'running' || s === 'in_progress') return 'running';
    if (s === 'error' || s === 'failed') return 'error';
    if (s === 'warning') return 'warning';
    if (s === 'pending') return 'pending';
    return 'pending';
  }

  get icon(): string {
    switch (this.normalizedStatus) {
      case 'success': return 'check_circle';
      case 'running': return 'autorenew';
      case 'error':   return 'error';
      case 'warning': return 'warning';
      default:        return 'schedule';
    }
  }

  get label(): string {
    return this.status || 'unknown';
  }
}
