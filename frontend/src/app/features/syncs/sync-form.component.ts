import { Component, OnInit, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { SyncService, CreateSyncInput } from '../../core/services/sync.service';
import { NotificationService } from '../../core/services/notification.service';
import { CronDisplayComponent } from '../../shared/components/cron-display/cron-display.component';

@Component({
  selector: 'app-sync-form',
  imports: [
    CommonModule, ReactiveFormsModule, RouterModule, MatButtonModule, MatIconModule,
    MatFormFieldModule, MatInputModule, MatSelectModule, MatProgressSpinnerModule,
    CronDisplayComponent,
  ],
  template: `
    <!-- Page banner -->
    <div class="page-banner">
      <div class="banner-inner">
        <div class="banner-left">
          <nav class="breadcrumb" aria-label="Breadcrumb">
            <a routerLink="/dashboard" class="bc-link">Home</a>
            <mat-icon class="bc-sep">chevron_right</mat-icon>
            <a routerLink="/syncs" class="bc-link">Syncs</a>
            <mat-icon class="bc-sep">chevron_right</mat-icon>
            <span class="bc-current">{{ isEdit ? 'Edit Sync' : 'New Sync' }}</span>
          </nav>
          <h1 class="banner-title">{{ isEdit ? 'Edit Sync' : 'Create Sync' }}</h1>
          <p class="banner-subtitle">{{ isEdit ? 'Update sync configuration.' : 'Configure a new DITA-to-knowledge-base syndication sync.' }}</p>
        </div>
      </div>
    </div>

    <div class="form-page">
      <form [formGroup]="form" (ngSubmit)="onSubmit()" class="sync-form">

        <!-- Basic info -->
        <section class="form-section">
          <h2 class="section-title">Basic Information</h2>
          <mat-form-field appearance="outline" class="form-field-full">
            <mat-label>Name</mat-label>
            <input matInput formControlName="name" placeholder="e.g. Salesforce Knowledge Sync">
            <mat-error *ngIf="form.get('name')?.hasError('required')">Name is required</mat-error>
          </mat-form-field>
        </section>

        <!-- Source & target -->
        <section class="form-section">
          <h2 class="section-title">Source & Target</h2>
          <div class="form-row">
            <mat-form-field appearance="outline" class="form-field">
              <mat-label>Source Adapter</mat-label>
              <mat-select formControlName="adapter_id">
                <mat-option value="deploy">Heretto Deploy</mat-option>
                <mat-option value="bundle">Bundle (DITA archive)</mat-option>
              </mat-select>
              <mat-error *ngIf="form.get('adapter_id')?.hasError('required')">Required</mat-error>
            </mat-form-field>

            <mat-form-field appearance="outline" class="form-field">
              <mat-label>Target Connector</mat-label>
              <mat-select formControlName="connector_id">
                <mat-option value="salesforce">Salesforce Knowledge</mat-option>
                <mat-option value="servicenow">ServiceNow Knowledge</mat-option>
                <mat-option value="zendesk">Zendesk Guide</mat-option>
                <mat-option value="noop">No-op (dry run)</mat-option>
              </mat-select>
              <mat-error *ngIf="form.get('connector_id')?.hasError('required')">Required</mat-error>
            </mat-form-field>
          </div>
        </section>

        <!-- Connection details -->
        <section class="form-section">
          <h2 class="section-title">Connection Details</h2>
          <div class="form-row">
            <mat-form-field appearance="outline" class="form-field">
              <mat-label>Organization ID</mat-label>
              <input matInput formControlName="org_id" placeholder="your-org-uuid">
              <mat-error *ngIf="form.get('org_id')?.hasError('required')">Required</mat-error>
            </mat-form-field>

            <mat-form-field appearance="outline" class="form-field">
              <mat-label>Deployment ID</mat-label>
              <input matInput formControlName="deployment_id" placeholder="deploy-uuid (optional)">
            </mat-form-field>
          </div>

          <mat-form-field appearance="outline" class="form-field-full">
            <mat-label>Credential ID</mat-label>
            <input matInput formControlName="credential_id" placeholder="credential-uuid (from Credentials)">
            <mat-hint>Reference to a stored credential in the platform</mat-hint>
          </mat-form-field>
        </section>

        <!-- Schedule -->
        <section class="form-section">
          <h2 class="section-title">Schedule</h2>
          <mat-form-field appearance="outline" class="form-field-full">
            <mat-label>Cron Expression</mat-label>
            <input matInput formControlName="cron_expression" placeholder="0 * * * * (hourly)">
            <mat-hint>Standard 5-field cron syntax: minute hour day-of-month month day-of-week</mat-hint>
            <mat-error *ngIf="form.get('cron_expression')?.hasError('required')">Required</mat-error>
          </mat-form-field>
          <div *ngIf="form.get('cron_expression')?.value" class="cron-preview">
            <mat-icon class="cron-icon">schedule</mat-icon>
            <app-cron-display [expression]="form.get('cron_expression')?.value ?? ''"></app-cron-display>
          </div>
        </section>

        <!-- Actions -->
        <div class="form-actions">
          <a mat-stroked-button routerLink="/syncs" class="cancel-btn">Cancel</a>
          <button mat-flat-button type="submit" class="save-btn" [disabled]="saving">
            <mat-spinner *ngIf="saving" diameter="16" class="btn-spinner"></mat-spinner>
            {{ isEdit ? 'Save Changes' : 'Create Sync' }}
          </button>
        </div>
      </form>
    </div>
  `,
  styles: [`
    .page-banner {
      background: linear-gradient(135deg, #011627 0%, #0d2137 100%);
      border-bottom: 1px solid rgba(255,255,255,0.06);
      padding: 0 28px;
      margin: -20px -24px 0;
    }
    .banner-inner { display: flex; padding: 24px 0; }
    .breadcrumb { display: flex; align-items: center; gap: 4px; margin-bottom: 8px; }
    .bc-link { font-size: 12px; color: rgba(255,255,255,0.5); text-decoration: none; }
    .bc-link:hover { color: #79ECDD; }
    .bc-sep { font-size: 14px; width: 14px; height: 14px; color: rgba(255,255,255,0.3); }
    .bc-current { font-size: 12px; color: rgba(255,255,255,0.55); }
    .banner-title { font-size: 22px; font-weight: 700; color: #fff; margin: 0 0 4px; }
    .banner-subtitle { font-size: 13px; color: rgba(255,255,255,0.5); margin: 0; }

    .form-page { max-width: 720px; padding: 28px 0; }
    .sync-form { display: flex; flex-direction: column; gap: 8px; }

    .form-section {
      background: #fff;
      border: 1px solid #dee2ec;
      border-radius: 4px;
      padding: 20px 24px;
    }
    .section-title {
      font-size: 13px; font-weight: 700; color: #1d1f2b;
      text-transform: uppercase; letter-spacing: 0.5px;
      margin: 0 0 16px;
      padding-bottom: 10px;
      border-bottom: 1px solid #f0f2f7;
    }
    .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .form-field { width: 100%; }
    .form-field-full { width: 100%; display: block; }

    .cron-preview {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-top: 8px;
      padding: 8px 12px;
      background: #f8f9fb;
      border-radius: 4px;
      border: 1px solid #dee2ec;
    }
    .cron-icon { font-size: 14px; width: 14px; height: 14px; color: #5e6e82; }

    .form-actions {
      display: flex;
      justify-content: flex-end;
      gap: 12px;
      padding-top: 8px;
    }
    .cancel-btn { border-color: #dee2ec; color: #5e6e82; }
    .save-btn {
      background: #011627 !important;
      color: #fff !important;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .btn-spinner { display: inline-block; }
  `],
})
export class SyncFormComponent implements OnInit {
  private destroyRef = inject(DestroyRef);
  private route = inject(ActivatedRoute);

  isEdit = false;
  saving = false;

  form = inject(FormBuilder).group({
    name:            ['', Validators.required],
    adapter_id:      ['deploy', Validators.required],
    connector_id:    ['salesforce', Validators.required],
    org_id:          ['', Validators.required],
    deployment_id:   [''],
    credential_id:   [''],
    cron_expression: ['0 * * * *', Validators.required],
  });

  constructor(
    private syncService: SyncService,
    private notifications: NotificationService,
    private router: Router,
  ) {}

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.isEdit = true;
      this.syncService.getById(id)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(sync => {
          this.form.patchValue({
            name:            sync.name,
            adapter_id:      sync.adapter_id,
            connector_id:    sync.connector_id,
            org_id:          sync.org_id,
            deployment_id:   sync.deployment_id ?? '',
            credential_id:   sync.credential_id ?? '',
            cron_expression: sync.cron_expression,
          });
        });
    }
  }

  onSubmit() {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    this.saving = true;

    const raw = this.form.getRawValue();
    const input: CreateSyncInput = {
      name:            raw.name!,
      adapter_id:      raw.adapter_id!,
      connector_id:    raw.connector_id!,
      org_id:          raw.org_id!,
      deployment_id:   raw.deployment_id ?? '',
      cron_expression: raw.cron_expression!,
      credential_id:   raw.credential_id || undefined,
    };

    this.syncService.create(input)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: sync => {
          this.notifications.success('Sync created successfully');
          this.router.navigate(['/syncs', sync.id]);
        },
        error: () => { this.saving = false; },
      });
  }
}
