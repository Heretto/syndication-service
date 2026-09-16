import { Component, OnInit, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { HopConfirmDialogComponent } from '@heretto/hop-ui';
import { interval, Subscription } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { SyncService, SyncConfig, SyncRun } from '../../core/services/sync.service';
import { NotificationService } from '../../core/services/notification.service';
import { StatusBadgeComponent } from '../../shared/components/status-badge/status-badge.component';
import { CronDisplayComponent } from '../../shared/components/cron-display/cron-display.component';
import { LocalDatePipe } from '../../shared/pipes/local-date.pipe';

@Component({
  selector: 'app-sync-detail',
  imports: [
    CommonModule, RouterModule, MatButtonModule, MatIconModule,
    MatDialogModule, MatProgressSpinnerModule, MatProgressBarModule,
    MatTabsModule, MatTooltipModule,
    StatusBadgeComponent, CronDisplayComponent, LocalDatePipe,
  ],
  template: `
    <div *ngIf="loading" class="loading-center">
      <mat-spinner diameter="36"></mat-spinner>
    </div>

    <div *ngIf="!loading && loadError" class="load-error">
      <mat-icon>error_outline</mat-icon>
      <p>Failed to load sync details. Please refresh the page.</p>
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
            <button mat-stroked-button class="action-banner-btn" [routerLink]="['/syncs', sync.id, 'edit']">
              <mat-icon>edit</mat-icon> Edit
            </button>
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

      <!-- Auto-deactivation callout -->
      <div *ngIf="showDeactivationCallout" class="deactivation-callout">
        <mat-icon>warning_amber</mat-icon>
        <div class="callout-body">
          <strong>Sync automatically disabled after repeated failures</strong>
          <p>This sync was disabled after too many consecutive failed runs. Review the errors in Recent Runs below, fix the underlying issue, then delete and recreate the sync to restart it.</p>
        </div>
      </div>

      <!-- Tabs -->
      <mat-tab-group class="detail-tabs" animationDuration="150ms">

        <!-- Recent Syncs tab -->
        <mat-tab>
          <ng-template mat-tab-label>
            Recent Syncs
            <span *ngIf="runsLoading" class="tab-spinner">
              <mat-spinner diameter="12"></mat-spinner>
            </span>
          </ng-template>
          <div class="tab-content">
            <section class="detail-card">
              <div *ngIf="!runsLoading && runs.length === 0" class="runs-empty">
                <mat-icon>history</mat-icon>
                <p>No syncs yet. Click "Sync Changes" to trigger the first sync.</p>
              </div>

              <div class="runs-table-wrap" *ngIf="runs.length > 0">
                <table class="runs-table">
                  <thead>
                    <tr>
                      <th>Status</th>
                      <th>Started</th>
                      <th>Duration</th>
                      <th class="num-col">Changed</th>
                      <th class="num-col">Removed</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    <ng-container *ngFor="let r of runs">
                      <!-- Main data row -->
                      <tr [class.row-running]="r.status === 'running'">
                        <td><app-status-badge [status]="r.status"></app-status-badge></td>
                        <td class="cell-time">{{ r.started_at | localDate:'MMM d, h:mm a' }}</td>
                        <td class="cell-duration">
                          <span *ngIf="r.completed_at">{{ duration(r) }}</span>
                          <span *ngIf="!r.completed_at" class="in-progress-text">In progress</span>
                        </td>
                        <td class="num-col">
                          <span *ngIf="r.changed_count != null" class="stat-badge stat-changed">{{ r.changed_count }}</span>
                          <span *ngIf="r.changed_count == null" class="cell-empty">—</span>
                        </td>
                        <td class="num-col">
                          <span *ngIf="r.removed_count != null && r.removed_count > 0" class="stat-badge stat-removed">{{ r.removed_count }}</span>
                          <span *ngIf="!r.removed_count" class="cell-empty">—</span>
                        </td>
                        <td class="cell-notes">
                          <ng-container *ngIf="r.error_message || r.warning_messages?.length; else noNotes">
                            <div *ngIf="r.error_message" class="note-inline note-error">
                              <mat-icon>error_outline</mat-icon>
                              <span class="note-text" [class.note-clamped]="!expandedNotes.has(r.id)">{{ r.error_message }}</span>
                            </div>
                            <div *ngFor="let w of r.warning_messages" class="note-inline note-warning">
                              <mat-icon>warning_amber</mat-icon>
                              <span class="note-text" [class.note-clamped]="!expandedNotes.has(r.id)">{{ w }}</span>
                            </div>
                            <button class="note-toggle" (click)="toggleNote(r.id)">
                              {{ expandedNotes.has(r.id) ? 'Show less' : 'Show more' }}
                            </button>
                          </ng-container>
                          <ng-template #noNotes>
                            <span class="cell-empty">—</span>
                          </ng-template>
                        </td>
                      </tr>
                      <!-- Progress row (running only) -->
                      <tr *ngIf="r.status === 'running'" class="row-progress">
                        <td colspan="6" class="progress-cell">
                          <ng-container *ngIf="r.total_count != null && r.total_count > 0; else indeterminate">
                            <mat-progress-bar mode="determinate" [value]="progressPercent(r)"></mat-progress-bar>
                            <span class="progress-label">{{ r.processed_count ?? 0 }} of {{ r.total_count }} completed</span>
                          </ng-container>
                          <ng-template #indeterminate>
                            <mat-progress-bar mode="indeterminate"></mat-progress-bar>
                            <span class="progress-label">Syncing…</span>
                          </ng-template>
                        </td>
                      </tr>
                    </ng-container>
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </mat-tab>

        <!-- Configuration tab -->
        <mat-tab label="Configuration">
          <div class="tab-content">
            <section class="detail-card">
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
                <div class="dl-row">
                  <dt>Publish Mode</dt>
                  <dd>{{ sync.publish_mode === 'draft' ? 'Save as draft' : 'Auto-publish' }}</dd>
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
          </div>
        </mat-tab>

      </mat-tab-group>
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

    /* Tabs */
    .detail-tabs { margin-top: 20px; }
    ::ng-deep .detail-tabs .mat-mdc-tab-header { border-bottom: 1px solid #dee2ec; }
    ::ng-deep .detail-tabs .mat-mdc-tab-body-wrapper { padding-top: 0; }
    .tab-content { padding: 20px 0; }
    .tab-spinner { display: inline-flex; margin-left: 8px; vertical-align: middle; }

    .detail-card { background: #fff; border: 1px solid #dee2ec; border-radius: 4px; overflow: hidden; }

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

    /* Runs table */
    .runs-table-wrap { overflow-x: auto; }
    .runs-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
    .runs-table thead tr { background: #f8f9fb; }
    .runs-table th { font-size: 11px; font-weight: 700; color: #5e6e82; text-transform: uppercase; letter-spacing: 0.4px; padding: 8px 14px; text-align: left; border-bottom: 1px solid #dee2ec; white-space: nowrap; }
    .runs-table td { padding: 9px 14px; border-bottom: 1px solid #f0f2f7; vertical-align: middle; color: #1d1f2b; }
    .runs-table tbody tr:last-child td { border-bottom: none; }
    .runs-table tbody tr.row-running { background: #f5fbff; }
    .runs-table th.num-col,
    .runs-table td.num-col { text-align: center; }
    .cell-time { white-space: nowrap; font-size: 12px; }
    .cell-duration { white-space: nowrap; font-size: 12px; color: #5e6e82; }
    .in-progress-text { font-size: 11px; font-style: italic; color: #0052cc; }
    .cell-empty { color: #bdc5d1; }
    .cell-notes { max-width: 220px; }

    .stat-badge { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 3px; }
    .stat-changed { background: rgba(0,82,204,0.1); color: #0052cc; }
    .stat-removed { background: rgba(222,53,11,0.1); color: #b22a09; }

    .note-inline { display: flex; align-items: flex-start; gap: 5px; margin-bottom: 4px; }
    .note-inline mat-icon { font-size: 13px; width: 13px; height: 13px; flex-shrink: 0; margin-top: 1px; }
    .note-text { font-size: 11.5px; line-height: 1.45; }
    .note-clamped { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
    .note-toggle {
      background: none; border: none; padding: 2px 0 0; cursor: pointer;
      font-size: 11px; color: #0052cc; text-decoration: underline;
      display: block; margin-top: 2px; margin-left: 18px;
    }
    .note-toggle:hover { color: #0039a6; }
    .note-warning { color: #7c4000; }
    .note-warning mat-icon { color: #e65100; }
    .note-error { color: #b22a09; }
    .note-error mat-icon { color: #de350b; }

    /* Progress sub-row */
    .row-progress td { padding: 0 14px 10px; border-bottom: none; }
    .progress-cell { padding: 0 14px 10px !important; }
    .progress-label { display: block; font-size: 11px; color: #5e6e82; margin-top: 4px; }

    .load-error { display: flex; align-items: center; gap: 10px; padding: 20px 24px; color: #b22a09; font-size: 13px; }
    .load-error mat-icon { color: #de350b; }

    .deactivation-callout { display: flex; align-items: flex-start; gap: 12px; background: #fff8f6; border: 1px solid #f5c6bc; border-radius: 4px; padding: 14px 18px; margin: 16px 0 0; }
    .deactivation-callout > mat-icon { color: #e65100; flex-shrink: 0; margin-top: 1px; }
    .callout-body strong { font-size: 13px; font-weight: 600; color: #7c2d0e; display: block; margin-bottom: 4px; }
    .callout-body p { font-size: 12.5px; color: #7c2d0e; margin: 0; line-height: 1.5; }

    .not-found { display: flex; flex-direction: column; align-items: center; padding: 80px 24px; text-align: center; color: #5e6e82; }
    .not-found mat-icon { font-size: 48px; width: 48px; height: 48px; margin-bottom: 16px; }
    .not-found h2 { font-size: 18px; color: #3d4460; margin: 0 0 20px; }
  `],
})
export class SyncDetailComponent implements OnInit {
  private destroyRef = inject(DestroyRef);
  private route = inject(ActivatedRoute);
  private _pollSub: Subscription | null = null;

  sync: SyncConfig | null = null;
  runs: SyncRun[] = [];
  loading = true;
  loadError = false;
  runsLoading = false;
  expandedNotes = new Set<string>();

  get showDeactivationCallout(): boolean {
    return !this.sync?.is_active && this.runs.length > 0 && this.runs[0].status === 'failed';
  }

  toggleNote(runId: string): void {
    if (this.expandedNotes.has(runId)) {
      this.expandedNotes.delete(runId);
    } else {
      this.expandedNotes.add(runId);
    }
  }

  progressPercent(run: SyncRun): number {
    if (!run.total_count) return 0;
    return Math.round(((run.processed_count ?? 0) / run.total_count) * 100);
  }

  duration(run: SyncRun): string {
    if (!run.started_at || !run.completed_at) return '';
    const ms = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime();
    const secs = Math.round(ms / 1000);
    if (secs < 60) return `${secs}s`;
    const mins = Math.floor(secs / 60);
    const rem = secs % 60;
    return rem > 0 ? `${mins}m ${rem}s` : `${mins}m`;
  }

  constructor(
    private syncService: SyncService,
    private notifications: NotificationService,
    private dialog: MatDialog,
    private router: Router,
  ) {
    this.destroyRef.onDestroy(() => {
      this._pollSub?.unsubscribe();
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
        error: () => { this.loading = false; this.loadError = true; },
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
        error: () => this.notifications.error('Failed to trigger sync. Please try again.'),
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
        confirmText: 'Force Resync',
      },
    });
    ref.afterClosed().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(confirmed => {
      if (!confirmed) return;
      this.syncService.trigger(syncId, true)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: () => {
            this.notifications.success('Full resync triggered');
            this._startRunPolling(syncId);
          },
          error: () => this.notifications.error('Failed to trigger full resync. Please try again.'),
        });
    });
  }

  private _startRunPolling(syncId: string): void {
    this._pollSub?.unsubscribe();
    this.runsLoading = true;

    let polls = 0;
    this._pollSub = interval(3000).pipe(
      switchMap(() => this.syncService.getRuns(syncId)),
    ).subscribe({
      next: runs => {
        this.runs = [...runs];
        polls++;
        // Only watch the most recent run — old stuck runs must not block the spinner
        const latestIsRunning = runs.length > 0 && runs[0].status === 'running';
        if (!latestIsRunning || polls >= 200) {  // 200 × 3s ≈ 10 min deadline
          this.runsLoading = false;
          this._pollSub?.unsubscribe();
          this._pollSub = null;
          if (!latestIsRunning) {
            // Refresh sync config so Last Synced / high_water_mark updates
            this.syncService.getById(syncId)
              .pipe(takeUntilDestroyed(this.destroyRef))
              .subscribe(sync => { this.sync = sync; });
          }
        }
      },
      error: () => { this.runsLoading = false; },
    });
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
