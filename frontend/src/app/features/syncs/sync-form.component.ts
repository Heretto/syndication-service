import { Component, OnInit, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormsModule, FormBuilder, FormArray, FormGroup, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDividerModule } from '@angular/material/divider';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatRadioModule } from '@angular/material/radio';
import { SyncService, CreateSyncInput, UpdateSyncInput } from '../../core/services/sync.service';
import { CredentialService, Credential, CredentialCreate } from '../../core/services/credential.service';
import { ApiService } from '../../core/services/api.service';
import { NotificationService } from '../../core/services/notification.service';
import { CronBuilderComponent } from '../../shared/components/cron-builder/cron-builder.component';

// ── Static field definitions ──────────────────────────────────────────────────

interface CredField {
  key: string;
  label: string;
  inputType?: 'text' | 'password';
  hint?: string;
  defaultVal?: string;
}

const CRED_FIELDS: Record<string, CredField[]> = {
  salesforce: [
    { key: 'instance_url',      label: 'Instance URL',            hint: 'https://myorg.my.salesforce.com' },
    { key: 'client_id',         label: 'Consumer Key',            hint: 'External Client App Consumer Key' },
    { key: 'client_secret',     label: 'Consumer Secret',         inputType: 'password' },
    { key: 'api_version',       label: 'API Version',             defaultVal: '65.0' },
    { key: 'knowledge_type',    label: 'Knowledge Object API Name', defaultVal: 'Knowledge__kav' },
    { key: 'external_id_field', label: 'Tracking Field API Name', defaultVal: 'Heretto_UUID__c' },
    { key: 'api_key',           label: 'Heretto Deploy API Key',  inputType: 'password' },
    { key: 'base_url',          label: 'Deploy API Base URL',     hint: 'https://yourorg.deploy.heretto.com (no /v4)' },
  ],
};

const DEFAULT_MAPPINGS: Record<string, Record<string, string>> = {
  salesforce: { title: 'Title', short_description: 'Summary__c', html_body: 'Answer__c' },
};

const CONNECTOR_LABELS: Record<string, string> = {
  salesforce: 'Salesforce Knowledge',
  noop:       'No-op',
};

const TARGET_PLACEHOLDERS: Record<string, string> = {
  salesforce: 'e.g. Title, Answer__c, Summary__c',
};

// ── Component ─────────────────────────────────────────────────────────────────

@Component({
  selector: 'app-sync-form',
  imports: [
    CommonModule, ReactiveFormsModule, FormsModule, RouterModule,
    MatButtonModule, MatIconModule, MatFormFieldModule, MatInputModule,
    MatSelectModule, MatProgressSpinnerModule, MatDividerModule, MatTooltipModule,
    MatCheckboxModule, MatRadioModule, CronBuilderComponent,
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
          <p class="banner-subtitle">{{ isEdit ? 'Update sync configuration.' : 'Configure a new Heretto to Knowledge Base syndication sync.' }}</p>
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
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline" class="form-field">
              <mat-label>Target Connector</mat-label>
              <mat-select formControlName="connector_id">
                <mat-option value="salesforce">Salesforce Knowledge</mat-option>
                <mat-option value="noop">No-op (dry run)</mat-option>
              </mat-select>
            </mat-form-field>
          </div>
        </section>

        <!-- Source connection: Heretto Deploy -->
        <section class="form-section">
          <h2 class="section-title">Source — Heretto Deploy</h2>
          <mat-form-field appearance="outline" class="form-field-full">
            <mat-label>Deployment ID</mat-label>
            <input matInput formControlName="deployment_id" placeholder="deployment-uuid">
            <mat-hint>The Deployment ID for the content in Heretto.</mat-hint>
          </mat-form-field>
        </section>

        <!-- Target connection: connector credential -->
        <section class="form-section" *ngIf="form.get('connector_id')?.value !== 'noop'">
          <h2 class="section-title">Target Connection — {{ connectorLabel }}</h2>

          <!-- Existing credential picker -->
          <div *ngIf="credsLoading" class="creds-loading">
            <mat-spinner diameter="16"></mat-spinner>
            <span>Loading credentials…</span>
          </div>

          <mat-form-field appearance="outline" class="form-field-full" *ngIf="!credsLoading">
            <mat-label>Credential</mat-label>
            <mat-select formControlName="credential_id">
              <mat-option [value]="null">— None selected —</mat-option>
              <mat-option *ngFor="let c of credentials" [value]="c.id">{{ c.name }}</mat-option>
            </mat-select>
            <mat-hint>Stored credentials for {{ connectorLabel }}. Secrets are encrypted at rest.</mat-hint>
          </mat-form-field>

          <!-- Saved credentials list with delete -->
          <div *ngIf="!credsLoading && credentials.length > 0" class="cred-manage-list">
            <div class="cred-manage-row" *ngFor="let c of credentials">
              <mat-icon class="cred-manage-icon">key</mat-icon>
              <span class="cred-manage-name">{{ c.name }}</span>
              <button mat-icon-button type="button" class="cred-delete-btn"
                      (click)="deleteCredential(c)"
                      [attr.aria-label]="'Delete credential ' + c.name"
                      matTooltip="Delete">
                <mat-icon>delete</mat-icon>
              </button>
            </div>
          </div>

          <!-- Create new credential toggle -->
          <div class="new-cred-toggle">
            <button mat-stroked-button type="button" (click)="showNewCred = !showNewCred" class="new-cred-btn">
              <mat-icon>{{ showNewCred ? 'expand_less' : 'add' }}</mat-icon>
              {{ showNewCred ? 'Cancel' : 'Create new credential' }}
            </button>
          </div>

          <!-- Inline create-new credential form -->
          <div *ngIf="showNewCred" class="new-cred-form">
            <mat-divider class="cred-divider"></mat-divider>
            <p class="cred-form-title">New {{ connectorLabel }} credential</p>

            <mat-form-field appearance="outline" class="form-field-full">
              <mat-label>Credential Name</mat-label>
              <input matInput [(ngModel)]="newCredName" [ngModelOptions]="{standalone: true}"
                     placeholder="e.g. Production Salesforce">
            </mat-form-field>

            <div class="cred-fields-grid">
              <mat-form-field appearance="outline" *ngFor="let f of credentialFields" class="cred-field">
                <mat-label>{{ f.label }}</mat-label>
                <input matInput
                       [type]="f.inputType || 'text'"
                       [(ngModel)]="newCredValues[f.key]"
                       [ngModelOptions]="{standalone: true}"
                       [placeholder]="f.hint || f.defaultVal || ''">
                <mat-hint *ngIf="f.hint">{{ f.hint }}</mat-hint>
              </mat-form-field>
            </div>

            <div class="cred-actions">
              <button mat-flat-button type="button" (click)="saveNewCredential()" [disabled]="savingCred" class="save-cred-btn">
                <mat-spinner *ngIf="savingCred" diameter="14" class="btn-spinner"></mat-spinner>
                Save Credential
              </button>
            </div>
          </div>
        </section>

        <!-- Schedule -->
        <section class="form-section">
          <h2 class="section-title">Schedule</h2>
          <div class="manual-only-row">
            <mat-checkbox formControlName="manual_only" color="primary">
              Manual sync only — no automatic schedule
            </mat-checkbox>
            <p class="manual-only-hint" *ngIf="form.get('manual_only')?.value">
              This sync will only run when triggered manually from the sync detail page.
            </p>
          </div>
          <div *ngIf="!form.get('manual_only')?.value" class="cron-builder-wrap">
            <app-cron-builder formControlName="cron_expression"></app-cron-builder>
          </div>

          <div class="publish-mode-row">
            <p class="publish-mode-label">Publish Mode</p>
            <mat-radio-group formControlName="publish_mode" class="publish-mode-group">
              <mat-radio-button value="auto" color="primary" class="publish-mode-option">
                <span class="pm-option-title">Auto-publish</span>
                <span class="pm-option-desc">Articles are published to Salesforce Knowledge immediately after sync.</span>
              </mat-radio-button>
              <mat-radio-button value="draft" color="primary" class="publish-mode-option">
                <span class="pm-option-title">Save as draft</span>
                <span class="pm-option-desc">Articles are saved as drafts and must be published manually in Salesforce.</span>
              </mat-radio-button>
            </mat-radio-group>
          </div>
        </section>

        <!-- Field mapping -->
        <section class="form-section">
          <h2 class="section-title">Field Mapping</h2>
          <p class="mapping-hint">
            Map Heretto Deploy article fields to the corresponding fields in your target knowledge base.
          </p>

          <!-- Column headers -->
          <div class="mapping-header" *ngIf="mappingArray.length > 0">
            <span class="mapping-col-label">Heretto Deploy Field</span>
            <span class="mapping-arrow-spacer"></span>
            <span class="mapping-col-label">{{ connectorFieldLabel }} Field</span>
            <span class="mapping-remove-spacer"></span>
          </div>

          <div formArrayName="mapping" class="mapping-list">
            <div *ngFor="let row of mappingArray.controls; let i = index"
                 [formGroupName]="i" class="mapping-row">

              <!-- Left: Deploy IR field -->
              <mat-form-field appearance="outline" class="mapping-field">
                <mat-select formControlName="ir_field" placeholder="Select Deploy field">
                  <mat-option *ngFor="let f of sourceFields" [value]="f.key">
                    {{ f.label }} ({{ f.key }})
                  </mat-option>
                </mat-select>
              </mat-form-field>

              <mat-icon class="mapping-arrow">arrow_forward</mat-icon>

              <!-- Right: target field — dropdown when SF fields loaded, text input otherwise -->
              <mat-form-field appearance="outline" class="mapping-field">
                <mat-label>{{ connectorFieldLabel }} Field</mat-label>
                <mat-select *ngIf="targetFields.length > 0"
                            formControlName="target_field"
                            placeholder="Select field">
                  <mat-option *ngFor="let f of targetFields" [value]="f.api_name">
                    {{ f.label }} ({{ f.api_name }})
                  </mat-option>
                </mat-select>
                <input *ngIf="targetFields.length === 0"
                       matInput formControlName="target_field"
                       [placeholder]="targetFieldPlaceholder">
                <mat-hint *ngIf="targetFieldsLoading">Loading Salesforce fields…</mat-hint>
              </mat-form-field>

              <button mat-icon-button type="button" (click)="removeMappingRow(i)"
                      class="remove-row-btn" aria-label="Remove row">
                <mat-icon>remove_circle_outline</mat-icon>
              </button>
            </div>
          </div>

          <button mat-stroked-button type="button" (click)="addMappingRow()" class="add-row-btn">
            <mat-icon>add</mat-icon> Add Field
          </button>
        </section>

        <!-- Data Category Mapping (Salesforce only) -->
        <section class="form-section" *ngIf="form.get('connector_id')?.value === 'salesforce'">
          <h2 class="section-title">Data Category Mapping</h2>
          <p class="mapping-hint">
            Map Heretto Deploy taxonomy groups to Salesforce Data Category groups.
            Values within each group pass through unchanged — the Deploy taxonomy value
            must match the SF Data Category API name exactly.
          </p>

          <div class="mapping-header" *ngIf="categoryMapArray.length > 0">
            <span class="mapping-col-label">Deploy Taxonomy Group</span>
            <span class="mapping-arrow-spacer"></span>
            <span class="mapping-col-label">Salesforce Category Group</span>
            <span class="mapping-remove-spacer"></span>
          </div>

          <div formArrayName="category_mapping" class="mapping-list">
            <div *ngFor="let row of categoryMapArray.controls; let i = index"
                 [formGroupName]="i" class="mapping-row">
              <mat-form-field appearance="outline" class="mapping-field">
                <mat-label>Deploy Taxonomy Group</mat-label>
                <input matInput formControlName="deploy_group" placeholder="e.g. Audiences">
              </mat-form-field>
              <mat-icon class="mapping-arrow">arrow_forward</mat-icon>
              <mat-form-field appearance="outline" class="mapping-field">
                <mat-label>Salesforce Category Group</mat-label>
                <mat-select *ngIf="sfCategoryGroups.length > 0"
                            formControlName="sf_group"
                            placeholder="Select group">
                  <mat-option *ngFor="let g of sfCategoryGroups" [value]="g.name">
                    {{ g.label }} ({{ g.name }})
                  </mat-option>
                </mat-select>
                <input *ngIf="sfCategoryGroups.length === 0"
                       matInput formControlName="sf_group"
                       placeholder="e.g. Audiences">
                <mat-hint *ngIf="sfCategoryGroupsLoading">Loading Salesforce category groups…</mat-hint>
              </mat-form-field>
              <button mat-icon-button type="button" (click)="removeCategoryRow(i)"
                      class="remove-row-btn" aria-label="Remove row">
                <mat-icon>remove_circle_outline</mat-icon>
              </button>
            </div>
          </div>

          <button mat-stroked-button type="button" (click)="addCategoryRow()" class="add-row-btn">
            <mat-icon>add</mat-icon> Add Category Group
          </button>
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

    /* Credentials */
    .creds-loading { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #5e6e82; margin-bottom: 12px; }
    .cred-manage-list { margin: 4px 0 8px; border: 1px solid #dee2ec; border-radius: 4px; overflow: hidden; }
    .cred-manage-row { display: flex; align-items: center; gap: 8px; padding: 6px 10px 6px 12px; border-bottom: 1px solid #f0f2f7; }
    .cred-manage-row:last-child { border-bottom: none; }
    .cred-manage-icon { font-size: 14px; width: 14px; height: 14px; color: #5e6e82; flex-shrink: 0; }
    .cred-manage-name { flex: 1; font-size: 13px; color: #1d1f2b; }
    .cred-delete-btn { color: #5e6e82 !important; width: 28px; height: 28px; line-height: 28px; flex-shrink: 0; }
    .cred-delete-btn:hover { color: #de350b !important; }
    .cred-delete-btn mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .new-cred-toggle { margin-top: 8px; }
    .new-cred-btn { border-color: #dee2ec; color: #5e6e82; font-size: 12.5px; }
    .new-cred-form { margin-top: 12px; }
    .cred-divider { margin-bottom: 16px; }
    .cred-form-title { font-size: 12.5px; font-weight: 600; color: #3b4563; margin: 0 0 14px; }
    .cred-fields-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; }
    .cred-field { width: 100%; }
    .cred-actions { margin-top: 8px; display: flex; justify-content: flex-end; }
    .save-cred-btn {
      background: #011627 !important; color: #fff !important;
      font-size: 13px; display: flex; align-items: center; gap: 6px;
    }

    /* Field mapping */
    .mapping-hint { font-size: 12.5px; color: #5e6e82; margin: 0 0 14px; line-height: 1.5; }

    .deploy-fields-ref {
      background: #f4f6fa;
      border: 1px solid #dee2ec;
      border-radius: 4px;
      margin-bottom: 16px;
      overflow: hidden;
    }
    .ref-toggle {
      width: 100%;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 9px 14px;
      background: none;
      border: none;
      cursor: pointer;
      gap: 8px;
    }
    .ref-toggle:hover { background: #edf0f6; }
    .ref-label { font-size: 11.5px; font-weight: 600; color: #3b4563; text-transform: uppercase; letter-spacing: 0.3px; margin: 0; }
    .ref-chevron { font-size: 16px; width: 16px; height: 16px; color: #5e6e82; flex-shrink: 0; }
    .ref-fields { display: flex; flex-direction: column; gap: 4px; padding: 0 14px 10px; }
    .ref-field { font-size: 12px; color: #5e6e82; }
    .ref-field code {
      font-family: 'Roboto Mono', monospace;
      font-size: 11.5px;
      background: #e4e8f0;
      padding: 1px 5px;
      border-radius: 3px;
      color: #1d1f2b;
    }

    .mapping-header {
      display: grid;
      grid-template-columns: 1fr 26px 1fr 40px;
      gap: 8px;
      margin-bottom: 4px;
      padding: 0 2px;
    }
    .mapping-col-label { font-size: 11px; font-weight: 600; color: #3b4563; text-transform: uppercase; letter-spacing: 0.4px; }
    .mapping-arrow-spacer { width: 26px; }
    .mapping-remove-spacer { width: 40px; }

    .mapping-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
    .mapping-row {
      display: grid;
      grid-template-columns: 1fr auto 1fr auto;
      align-items: center;
      gap: 8px;
    }
    .mapping-field { width: 100%; }
    .mapping-arrow { font-size: 18px; width: 18px; height: 18px; color: #5e6e82; flex-shrink: 0; }
    .remove-row-btn { color: #de350b !important; flex-shrink: 0; }
    .add-row-btn { border-color: #dee2ec; color: #5e6e82; font-size: 12.5px; }

    /* Manual-only schedule toggle */
    .manual-only-row { margin-bottom: 4px; }
    .manual-only-hint {
      font-size: 12px; color: #5e6e82; margin: 6px 0 0 30px; line-height: 1.5;
    }
    .cron-builder-wrap { margin-top: 12px; }

    /* Publish mode */
    .publish-mode-row { margin-top: 20px; padding-top: 16px; border-top: 1px solid #f0f2f7; }
    .publish-mode-label { font-size: 12px; font-weight: 600; color: #3b4563; text-transform: uppercase; letter-spacing: 0.4px; margin: 0 0 10px; }
    .publish-mode-group { display: flex; flex-direction: column; gap: 10px; }
    .publish-mode-option { display: flex; align-items: flex-start; }
    .pm-option-title { font-size: 13.5px; font-weight: 600; color: #1d1f2b; display: block; }
    .pm-option-desc { font-size: 12px; color: #5e6e82; display: block; margin-top: 2px; line-height: 1.4; }

    /* Actions */
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
  private destroyRef  = inject(DestroyRef);
  private route       = inject(ActivatedRoute);
  private fb          = inject(FormBuilder);
  private syncService = inject(SyncService);
  private credService = inject(CredentialService);
  private notifications = inject(NotificationService);
  private router      = inject(Router);
  private api         = inject(ApiService);

  isEdit   = false;
  saving   = false;
  private editId: string | null = null;

  // Credential state
  credentials:  Credential[] = [];
  credsLoading  = false;
  showNewCred   = false;
  savingCred    = false;
  newCredName   = '';
  newCredValues: Record<string, string> = {};

  // Dynamic field lists
  sourceFields: { key: string; label: string }[] = [];
  targetFields: { api_name: string; label: string }[] = [];
  targetFieldsLoading = false;
  sfCategoryGroups: { name: string; label: string }[] = [];
  sfCategoryGroupsLoading = false;

  form = this.fb.group({
    name:             ['', Validators.required],
    adapter_id:       ['deploy', Validators.required],
    connector_id:     ['salesforce', Validators.required],
    deployment_id:    [''],
    credential_id:    [null as string | null],
    manual_only:      [false],
    cron_expression:  ['0 9 * * *'],
    publish_mode:     ['auto'],
    mapping:          this.fb.array<FormGroup>([]),
    category_mapping: this.fb.array<FormGroup>([]),
  });

  get mappingArray(): FormArray {
    return this.form.get('mapping') as FormArray;
  }

  get categoryMapArray(): FormArray {
    return this.form.get('category_mapping') as FormArray;
  }

  get connectorLabel(): string {
    return CONNECTOR_LABELS[this.form.get('connector_id')?.value ?? ''] ?? 'Target';
  }

  get connectorFieldLabel(): string {
    return CONNECTOR_LABELS[this.form.get('connector_id')?.value ?? ''] ?? 'Target';
  }

  get targetFieldPlaceholder(): string {
    return TARGET_PLACEHOLDERS[this.form.get('connector_id')?.value ?? ''] ?? 'e.g. Title';
  }

  get credentialFields(): CredField[] {
    return CRED_FIELDS[this.form.get('connector_id')?.value ?? ''] ?? [];
  }

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.isEdit = true;
      this.editId = id;
      this.syncService.getById(id)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(sync => {
          const isManualOnly = !sync.cron_expression;
          this.form.patchValue({
            name:            sync.name,
            adapter_id:      sync.adapter_id,
            connector_id:    sync.connector_id,
            deployment_id:   sync.deployment_id ?? '',
            credential_id:   sync.credential_id ?? null,
            manual_only:     isManualOnly,
            cron_expression: sync.cron_expression ?? '0 9 * * *',
            publish_mode:    sync.publish_mode ?? 'auto',
          });
          const rawMapping = { ...(sync.mapping || {}) };
          const categoryMap = (rawMapping['category_map'] as Record<string, string>) || {};
          delete rawMapping['category_map'];

          this.mappingArray.clear();
          for (const [irField, targetField] of Object.entries(rawMapping)) {
            this.mappingArray.push(this._createMappingRow(irField, String(targetField)));
          }
          this.categoryMapArray.clear();
          for (const [deployGroup, sfGroup] of Object.entries(categoryMap)) {
            this.categoryMapArray.push(this._createCategoryRow(deployGroup, sfGroup));
          }
          this._loadCredentials(sync.connector_id);
          this._resetNewCredForm(sync.connector_id);
          this._loadSourceFields();
          if (sync.credential_id) {
            this._loadTargetFields(sync.credential_id);
          }
          this.form.get('credential_id')!.valueChanges
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe(credId => this._loadTargetFields(credId));
        });
    } else {
      const initialConnector = this.form.get('connector_id')!.value;
      this._applyDefaultMapping(initialConnector);
      this._loadCredentials(initialConnector);
      this._resetNewCredForm(initialConnector);
      this._loadSourceFields();
      this.form.get('credential_id')!.valueChanges
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(credId => this._loadTargetFields(credId));

      // Reload credentials and reset defaults when connector changes
      this.form.get('connector_id')!.valueChanges
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(connectorId => {
          this._applyDefaultMapping(connectorId);
          this._loadCredentials(connectorId);
          this.form.get('credential_id')!.setValue(null);
          this.showNewCred = false;
          this._resetNewCredForm(connectorId);
          this.targetFields = [];
          this.sfCategoryGroups = [];
        });

      // Auto-populate mapping when a deployment is first connected
      this.form.get('deployment_id')!.valueChanges
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(depId => {
          if (depId && this.mappingArray.length === 0) {
            this._applyDefaultMapping(this.form.get('connector_id')!.value);
          }
        });
    }
  }

  private _loadSourceFields(): void {
    this.api.get<{ key: string; label: string }[]>('/fields/source')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: fields => this.sourceFields = fields,
        error: () => this.notifications.error('Failed to load source fields.'),
      });
  }

  private _loadTargetFields(credentialId: string | null): void {
    const connectorId = this.form.get('connector_id')?.value;
    if (!credentialId || connectorId !== 'salesforce') {
      this.targetFields = [];
      this.sfCategoryGroups = [];
      return;
    }
    this.targetFieldsLoading = true;
    this.api.get<{ api_name: string; label: string }[]>('/fields/target', {
      credential_id: credentialId,
      connector_id: connectorId,
    }).pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: fields => { this.targetFields = fields; this.targetFieldsLoading = false; },
        error: () => { this.targetFields = []; this.targetFieldsLoading = false; },
      });

    this.sfCategoryGroupsLoading = true;
    this.api.get<{ name: string; label: string }[]>('/fields/categories/target', {
      credential_id: credentialId,
      connector_id: connectorId,
    }).pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: groups => { this.sfCategoryGroups = groups; this.sfCategoryGroupsLoading = false; },
        error: () => { this.sfCategoryGroups = []; this.sfCategoryGroupsLoading = false; },
      });
  }

  private _loadCredentials(connectorId: string | null) {
    if (!connectorId || connectorId === 'noop') {
      this.credentials = [];
      return;
    }
    this.credsLoading = true;
    this.credService.list(connectorId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next:  creds => { this.credentials = creds; this.credsLoading = false; },
        error: ()    => { this.credsLoading = false; },
      });
  }

  private _resetNewCredForm(connectorId: string | null) {
    this.newCredName   = '';
    this.newCredValues = {};
    for (const f of CRED_FIELDS[connectorId ?? ''] ?? []) {
      this.newCredValues[f.key] = f.defaultVal ?? '';
    }
  }

  saveNewCredential() {
    if (!this.newCredName.trim()) {
      this.notifications.error('Credential name is required.');
      return;
    }
    const connectorId = this.form.get('connector_id')!.value ?? '';
    const credData: CredentialCreate = {
      type:        connectorId,
      name:        this.newCredName.trim(),
      credentials: { ...this.newCredValues },
    };
    this.savingCred = true;
    this.credService.create(credData)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: cred => {
          this.credentials = [...this.credentials, cred];
          this.form.get('credential_id')!.setValue(cred.id);
          this.showNewCred = false;
          this.savingCred  = false;
          this._resetNewCredForm(connectorId);
          this.notifications.success(`Credential "${cred.name}" saved.`);
        },
        error: () => { this.savingCred = false; },
      });
  }

  deleteCredential(cred: Credential) {
    if (!confirm(`Permanently delete credential "${cred.name}"? Any syncs using it will lose their connection.`)) {
      return;
    }
    this.credService.delete(cred.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.credentials = this.credentials.filter(c => c.id !== cred.id);
          if (this.form.get('credential_id')?.value === cred.id) {
            this.form.get('credential_id')!.setValue(null);
          }
          this.notifications.success(`Credential "${cred.name}" deleted.`);
        },
      });
  }

  private _createMappingRow(irField = '', targetField = ''): FormGroup {
    return this.fb.group({ ir_field: [irField], target_field: [targetField] });
  }

  private _applyDefaultMapping(connectorId: string | null): void {
    this.mappingArray.clear();
    this.categoryMapArray.clear();
    const defaults = DEFAULT_MAPPINGS[connectorId || ''] || {};
    for (const [irField, targetField] of Object.entries(defaults)) {
      this.mappingArray.push(this._createMappingRow(irField, targetField));
    }
  }

  addMappingRow(): void {
    this.mappingArray.push(this._createMappingRow());
  }

  removeMappingRow(index: number): void {
    this.mappingArray.removeAt(index);
  }

  private _createCategoryRow(deployGroup = '', sfGroup = ''): FormGroup {
    return this.fb.group({ deploy_group: [deployGroup], sf_group: [sfGroup] });
  }

  addCategoryRow(): void {
    this.categoryMapArray.push(this._createCategoryRow());
  }

  removeCategoryRow(index: number): void {
    this.categoryMapArray.removeAt(index);
  }

  private _buildCategoryMap(): Record<string, string> {
    const result: Record<string, string> = {};
    for (const row of this.categoryMapArray.value as Array<{ deploy_group: string; sf_group: string }>) {
      if (row.deploy_group && row.sf_group) {
        result[row.deploy_group] = row.sf_group;
      }
    }
    return result;
  }

  private _buildMappingDict(): Record<string, unknown> {
    const result: Record<string, unknown> = {};
    for (const row of this.mappingArray.value as Array<{ ir_field: string; target_field: string }>) {
      if (row.ir_field && row.target_field) {
        result[row.ir_field] = row.target_field;
      }
    }
    const categoryMap = this._buildCategoryMap();
    if (Object.keys(categoryMap).length > 0) {
      result['category_map'] = categoryMap;
    }
    return result;
  }

  onSubmit() {
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    this.saving = true;
    const raw     = this.form.getRawValue();
    const mapping = this._buildMappingDict();
    const cronExpression = raw.manual_only ? null : (raw.cron_expression || null);

    if (this.isEdit && this.editId) {
      const input: UpdateSyncInput = {
        name:            raw.name ?? undefined,
        cron_expression: cronExpression,
        deployment_id:   raw.deployment_id || undefined,
        credential_id:   raw.credential_id ?? null,
        mapping,
        publish_mode:    raw.publish_mode ?? 'auto',
      };
      this.syncService.update(this.editId, input)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: sync => {
            this.notifications.success('Sync updated successfully');
            this.router.navigate(['/syncs', sync.id]);
          },
          error: () => {
            this.saving = false;
            this.notifications.error('Failed to update sync. Please try again.');
          },
        });
    } else {
      const input: CreateSyncInput = {
        name:            raw.name!,
        adapter_id:      raw.adapter_id!,
        connector_id:    raw.connector_id!,
        deployment_id:   raw.deployment_id ?? '',
        cron_expression: cronExpression,
        mapping,
        credential_id:   raw.credential_id || undefined,
        publish_mode:    raw.publish_mode ?? 'auto',
      };
      this.syncService.create(input)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: sync => {
            this.notifications.success('Sync created successfully');
            this.router.navigate(['/syncs', sync.id]);
          },
          error: () => {
            this.saving = false;
            this.notifications.error('Failed to create sync. Please try again.');
          },
        });
    }
  }
}
