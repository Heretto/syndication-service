import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { HopAdminComponent } from '@heretto/hop-ui';

@Component({
  selector: 'app-superadmin',
  imports: [CommonModule, MatIconModule, HopAdminComponent],
  template: `
    <div class="future-targets-banner">
      <mat-icon class="banner-icon">info_outline</mat-icon>
      <p class="banner-text">
        Future releases of the Syndication Service will include support for additional
        publishing targets, including ServiceNow and Zendesk. Connector registration
        and platform-level configuration for those integrations will be managed here.
      </p>
    </div>
    <hop-admin></hop-admin>
  `,
  styles: [`
    .future-targets-banner {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      background: #e8f4fd;
      border: 1px solid #b3d9f7;
      border-radius: 4px;
      padding: 14px 18px;
      margin: 0 0 24px;
    }
    :host-context([data-theme="dark"]) .future-targets-banner,
    @media (prefers-color-scheme: dark) {
      .future-targets-banner {
        background: rgba(100, 181, 246, 0.1);
        border-color: rgba(100, 181, 246, 0.3);
      }
    }
    .banner-icon {
      color: #0277bd;
      font-size: 20px;
      width: 20px;
      height: 20px;
      flex-shrink: 0;
      margin-top: 1px;
    }
    .banner-text {
      font-size: 13px;
      color: #01579b;
      line-height: 1.5;
      margin: 0;
    }
  `],
})
export class SuperadminComponent {}
