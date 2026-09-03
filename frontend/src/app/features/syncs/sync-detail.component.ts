import { Component, OnInit, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { HopConfirmDialogComponent } from '@heretto/hop-ui';
import { SyncService, SyncConfig, SyncRun } from '../../core/services/sync.service';
import { NotificationService } from '../../core/services/notification.service';
import { StatusBadgeComponent } from '../../shared/components/status-badge/status-badge.component';
import { CronDisplayComponent } from '../../shared/components/cron-display/cron-display.component';
import { LocalDatePipe } from '../../shared/pipes/local-date.pipe';

@Component({
  selector: 'app-sync-detail',
  imports: [
    CommonModule, RouterModule, MatButtonModule, MatIconModule,
    MatDialogModule, MatProgressSpinnerModule, MatTooltipModule,
    StatusBadgeComponent, CronDisplayComponent, LocalDatePipe,
  ],
  template: `
    <div *ngIf="loading" class="loading-center">
      <mat-spinner diameter="36"></mat-spinner>
    </div>

    <ng-container *ngIf="!loading && sync">
      <!-- Page banner -->
      <div class="page-banner">
        <div class="banner-inner">
          <div class="banner-left">
            <nav class="breadcrumb">
              <a routerLink="/dashboard" class="bc-link">Home</a>
              <mat-icon class="bc-sep">chevron_right</mat-icon>
              <a routerLink="/syncs" class="bc-link">Syncs</a>
              <mat-icon class="bc-sep">chevron_right</mat-icon>
              <span class="bc-current">{{ sync.name }}</span>
            </nav>
            <h1 class="banner-title">{{ sync.name }}</h1>
            <div class="banner-meta">
              <span class="pipeline-tag">{{ sync.adapter_id }} → {{ sync.connector_id }}</span>
              <span class="status-pill" [class.pill-active]="sync.is_active" [class.pill-inactive]="!sync.is_active">
                {{ sync.is_active ? 'Active' : 'Inactive' }}
              </span>
            </div>
          </div>
          <div class="banner-right">
            <button mat-stroked-button class="action-banner-btn" (click)="triggerNow()" matTooltip="Sync files changed since the last run">
              <mat-icon>play_arrow</mat-icon> Sync Changes
            </button>
            <button mat-stroked-button class="action-banner-btn" (click)="forceResync()" matTooltip="Fetch every topic from the source, ignoring the change cursor">
              <mat-icon>refresh</mat-icon> Full Resync
            </button>
            <button mat-stroked-button class="action-banner-btn action-danger" (click)="deactivate()">
              <mat-icon>delete</mat-icon> Delete
            </button>
          </div>
        </div>
      </div>

      <!-- Detail content -->
      <div class="detail-grid">
        <!-- Config card -->
        <section class="detail-card">
          <h2 class="card-title">Configuration</h2>
          <dl class="detail-list">
            <div class="dl-row">
              <dt>Sync ID</dt>
              <dd class="mono">{{ sync.id }}</dd>
            </div>
            <div class="dl-row">
              <dt>Organization</dt>
              <dd>{{ sync.org_id }}</dd>
            </div>
            <div class="dl-row" *ngIf="sync.deployment_id">
              <dt>Deployment ID</dt>
              <dd class="mono">{{ sync.deployment_id }}</dd>
            </div>
            <div class="dl-row" *ngIf="sync.credential_id">
              <dt>Credential ID</dt>
              <dd class="mono">{{ sync.credential_id }}</dd>
            </div>
            <div class="dl-row">
              <dt>Schedule</dt>
              <dd>
                <app-cron-display [expression]="sync.cron_expression"></app-cron-display>
                <span class="cron-raw" *ngIf="sync.cron_expression">({{ sync.cron_expression }})</span>
              </dd>
            </div>
            <div class="dl-row" *ngIf="sync.high_water_mark">
              <dt>Last Synced</dt>
              <dd>{{ sync.high_water_mark | localDate:'MMM d, yyyy h:mm a' }}</dd>
            </div>
            <div class="dl-row" *ngIf="sync.created_at">
              <dt>Created</dt>
              <dd>{{ sync.created_at | localDate:'MMM d, yyyy' }}</dd>
            </div>
          </dl>
        </section>

        <!-- Recent runs -->
        <section class="detail-card">
          <div class="card-header-row">
            <h2 class="card-title">Recent Runs</h2>
            <span *ngIf="runsLoading" class="runs-loading">
              <mat-spinner diameter="14"></mat-spinner>
            </span>
          </div>

          <div *ngIf="!runsLoading && runs.length === 0" class="runs-empty">
            <mat-icon>history</mat-icon>
            <p>No runs yet. Click "Sync Changes" to trigger the first sync.</p>
          </div>

          <div class="run-list" *ngIf="runs.length > 0">
            <div class="run-item" *ngFor="let r of runs">
              <div class="run-row">
                <app-status-badge [status]="r.status"></app-status-badge>
                <div class="run-info">
                  <span class="run-time">{{ r.started_at | localDate:'MMM d, h:mm a' }}</span>
                  <span *ngIf="r.completed_at" class="run-duration">
                    Completed {{ r.completed_at | localDate:'h:mm a' }}
                  </span>
                </div>
                <div class="run-stats" *ngIf="r.changed_count != null || r.removed_count != null">
                  <span *ngIf="r.changed_count != null" class="stat-badge stat-changed">
                    {{ r.changed_count }} changed
                  </span>
                  <span *ngIf="r.removed_count" class="stat-badge stat-removed">
                    {{ r.removed_count }} removed
                  </span>
                </div>
              </div>
              <div class="run-messages" *ngIf="r.error_message || (r.warning_messages && r.warning_messages.length)">
                <div class="run-msg run-msg-error" *ngIf="r.error_message">
                  <mat-icon>error_outline</mat-icon>
                  <span>{{ r.error_message }}</span>
                </div>
                <div class="run-msg run-msg-warning" *ngFor="let w of r.warning_messages">
                  <mat-icon>warning_amber</mat-icon>
                  <span>{{ w }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </ng-container>

    <div *ngIf="!loading && !sync" class="not-found">
      <mat-icon>search_off</mat-icon>
      <h2>Sync not found</h2>
      <a mat-stroked-button routerLink="/syncs">Back to Syncs</a>
    </div>
  `,
  styles: [`
    .loading-center { display: flex; justify-content: center; padding: 80px; }

    .page-banner {
      background: linear-gradient(135deg, #011627 0%, #0d2137 100%);
      border-bottom: 1px solid rgba(255,255,255,0.06);
      padding: 0 28px;
      margin: -20px -24px 0;
    }
    .banner-inner { display: flex; justify-content: space-between; align-items: center; padding: 24px 0; }
    .breadcrumb { display: flex; align-items: center; gap: 4px; margin-bottom: 8px; }
    .bc-link { font-size: 12px; color: rgba(255,255,255,0.5); text-decoration: none; }
    .bc-link:hover { color: #79ECDD; }
    .bc-sep { font-size: 14px; width: 14px; height: 14px; color: rgba(255,255,255,0.3); }
    .bc-current { font-size: 12px; color: rgba(255,255,255,0.55); }
    .banner-title { font-size: 22px; font-weight: 700; color: #fff; margin: 0 0 8px; }
    .banner-meta { display: flex; align-items: center; gap: 10px; }
    .pipeline-tag { font-size: 12px; color: rgba(255,255,255,0.6); background: rgba(255,255,255,0.08); padding: 2px 8px; border-radius: 3px; }
    .status-pill { font-size: 10.5px; font-weight: 700; padding: 2px 8px; border-radius: 3px; text-transform: uppercase; letter-spacing: 0.5px; }
    .pill-active { background: rgba(0,166,80,0.2); color: #79ECDD; }
    .pill-inactive { background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.5); }
    .banner-right { display: flex; gap: 10px; }
    .action-banner-btn { border-color: rgba(255,255,255,0.2) !important; color: rgba(255,255,255,0.8) !important; }
    .action-banner-btn:hover { border-color: rgba(255,255,255,0.5) !important; color: #fff !important; }
    .action-danger:hover { border-color: rgba(222,53,11,0.6) !important; color: #ff8a80 !important; }

    .detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; padding: 20px 0; }

    .detail-card { background: #fff; border: 1px solid #dee2ec; border-radius: 4px; overflow: hidden; }
    .card-title { font-size: 13px; font-weight: 700; color: #1d1f2b; text-transform: uppercase; letter-spacing: 0.5px; margin: 0; padding: 14px 18px; border-bottom: 1px solid #f0f2f7; }
    .card-header-row { display: flex; align-items: center; gap: 10px; padding: 14px 18px; border-bottom: 1px solid #f0f2f7; }
    .card-header-row .card-title { padding: 0; border: none; }
    .runs-loading { display: flex; }

    .detail-list { margin: 0; padding: 0; }
    .dl-row { display: flex; padding: 10px 18px; border-bottom: 1px solid #f8f9fb; }
    .dl-row:last-child { border-bottom: none; }
    .dl-row dt { width: 140px; flex-shrink: 0; font-size: 12px; font-weight: 600; color: #5e6e82; text-transform: uppercase; letter-spacing: 0.3px; margin: 0; }
    .dl-row dd { font-size: 13px; color: #1d1f2b; margin: 0; flex: 1; }
    .mono { font-family: 'Roboto Mono', monospace; font-size: 12px; }
    .cron-raw { font-size: 11px; color: #5e6e82; margin-left: 6px; font-family: 'Roboto Mono', monospace; }

    .runs-empty { display: flex; flex-direction: column; align-items: center; padding: 40px 24px; text-align: center; color: #5e6e82; }
    .runs-empty mat-icon { font-size: 36px; width: 36px; height: 36px; margin-bottom: 12px; }
    .runs-empty p { font-size: 13px; margin: 0; }

    .run-list { display: flex; flex-direction: column; }
    .run-item { border-bottom: 1px solid #f0f2f7; }
    .run-item:last-child { border-bottom: none; }
    .run-row { display: flex; align-items: center; gap: 10px; padding: 10px 18px; }
    .run-info { flex: 1; display: flex; flex-direction: column; }
    .run-time { font-size: 12px; font-weight: 600; color: #1d1f2b; }
    .run-duration { font-size: 11px; color: #5e6e82; }
    .run-stats { display: flex; gap: 5px; flex-shrink: 0; }
    .stat-badge { font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 3px; }
    .stat-changed { background: rgba(0,82,204,0.1); color: #0052cc; }
    .stat-removed { background: rgba(222,53,11,0.1); color: #b22a09; }

    .run-messages { display: flex; flex-direction: column; gap: 2px; padding: 0 18px 10px 18px; }
    .run-msg { display: flex; align-items: flex-start; gap: 6px; font-size: 11.5px; line-height: 1.5; }
    .run-msg mat-icon { font-size: 14px; width: 14px; height: 14px; flex-shrink: 0; margin-top: 1px; }
    .run-msg-error { color: #b22a09; }
    .run-msg-error mat-icon { color: #de350b; }
    .run-msg-warning { color: #7c4000; }
    .run-msg-warning mat-icon { color: #e65100; }

    .not-found { display: flex; flex-direction: column; align-items: center; padding: 80px 24px; text-align: center; color: #5e6e82; }
    .not-found mat-icon { font-size: 48px; width: 48px; height: 48px; margin-bottom: 16px; }
    .not-found h2 { font-size: 18px; color: #3d4460; margin: 0 0 20px; }
  `],
})
export class SyncDetailComponent implements OnInit {
  private destroyRef = inject(DestroyRef);
  private route = inject(ActivatedRoute);
  private _pollTimer: ReturnType<typeof setTimeout> | null = null;

  sync: SyncConfig | null = null;
  runs: SyncRun[] = [];
  loading = true;
  runsLoading = false;

  constructor(
    private syncService: SyncService,
    private notifications: NotificationService,
    private dialog: MatDialog,
    private router: Router,
  ) {
    this.destroyRef.onDestroy(() => {
      if (this._pollTimer !== null) clearTimeout(this._pollTimer);
    });
  }

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.syncService.getById(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: sync => {
          this.sync = sync;
          this.loading = false;
          this.loadRuns(id);
        },
        error: () => { this.loading = false; },
      });
  }

  private loadRuns(syncId: string) {
    this.runsLoading = true;
    this.syncService.getRuns(syncId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: runs => { this.runs = runs; this.runsLoading = false; },
        error: () => { this.runsLoading = false; },
      });
  }

  triggerNow() {
    if (!this.sync) return;
    const syncId = this.sync.id;
    this.syncService.trigger(syncId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.notifications.success('Sync triggered');
          this._startRunPolling(syncId);
        },
      });
  }

  forceResync() {
    if (!this.sync) return;
    const syncId = this.sync.id;
    const ref = this.dialog.open(HopConfirmDialogComponent, {
      data: {
        title: 'Force Full Resync',
        message:
          'This will fetch every topic from the source, bypassing the change cursor. ' +
          'It may take longer than a normal sync. Continue?',
        confirmLabel: 'Force Resync',
      },
    });
    ref.afterClosed().subscribe(confirmed => {
      if (!confirmed) return;
      this.syncService.trigger(syncId, true)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: () => {
            this.notifications.success('Full resync triggered');
            this._startRunPolling(syncId);
          },
        });
    });
  }

  private _startRunPolling(syncId: string, deadline = Date.now() + 10 * 60 * 1000): void {
    this.runsLoading = true;
    this._pollTimer = setTimeout(() => {
      this.syncService.getRuns(syncId)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: runs => {
            this.runs = runs;
            const hasRunning = runs.some(r => r.status === 'running');
            if (hasRunning && Date.now() < deadline) {
              this._startRunPolling(syncId, deadline);
            } else {
              this.runsLoading = false;
            }
          },
          error: () => { this.runsLoading = false; },
        });
    }, 3000);
  }

  deactivate() {
    if (!this.sync) return;
    const ref = this.dialog.open(HopConfirmDialogComponent, {
      data: {
        title: 'Delete Sync',
        message: `Permanently delete "${this.sync.name}"? This cannot be undone — all run history and records will be removed.`,
        confirmText: 'Delete',
      },
    });
    ref.afterClosed()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(confirmed => {
        if (confirmed && this.sync) {
          this.syncService.delete(this.sync.id)
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
              next: () => {
                this.notifications.success('Sync deleted');
                this.router.navigate(['/syncs']);
              },
            });
        }
      });
  }
}
