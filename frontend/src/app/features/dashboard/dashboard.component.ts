import { Component, OnInit, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { forkJoin } from 'rxjs';
import { SyncService, SyncConfig, SyncRun } from '../../core/services/sync.service';
import { StatusBadgeComponent } from '../../shared/components/status-badge/status-badge.component';
import { CronDisplayComponent } from '../../shared/components/cron-display/cron-display.component';
import { LocalDatePipe } from '../../shared/pipes/local-date.pipe';

@Component({
  selector: 'app-dashboard',
  imports: [
    CommonModule, RouterModule, MatIconModule, MatButtonModule,
    MatProgressSpinnerModule, StatusBadgeComponent, CronDisplayComponent, LocalDatePipe,
  ],
  template: `
    <!-- Page banner -->
    <div class="page-banner">
      <div class="banner-inner">
        <div class="banner-left">
          <h1 class="banner-title">Dashboard</h1>
          <p class="banner-subtitle">Overview of your syndication syncs and sync history.</p>
        </div>
        <div class="banner-right">
          <a mat-flat-button class="create-btn" routerLink="/syncs/new">
            <mat-icon>add</mat-icon> New Sync
          </a>
        </div>
      </div>
    </div>

    <!-- KPI tiles -->
    <div class="kpi-grid">
      <div class="kpi-tile">
        <div class="kpi-icon-wrap kpi-total"><mat-icon>sync</mat-icon></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ syncs.length }}</div>
          <div class="kpi-label">Total Syncs</div>
        </div>
      </div>
      <div class="kpi-tile">
        <div class="kpi-icon-wrap kpi-active"><mat-icon>check_circle</mat-icon></div>
        <div class="kpi-body">
          <div class="kpi-value kpi-value-active">{{ activeCount }}</div>
          <div class="kpi-label">Active</div>
        </div>
      </div>
      <div class="kpi-tile">
        <div class="kpi-icon-wrap kpi-runs"><mat-icon>history</mat-icon></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ recentRuns.length }}</div>
          <div class="kpi-label">Recent Syncs</div>
        </div>
      </div>
      <div class="kpi-tile" [class.kpi-tile-alert]="errorCount > 0">
        <div class="kpi-icon-wrap" [class.kpi-error]="errorCount > 0" [class.kpi-ok]="errorCount === 0">
          <mat-icon>{{ errorCount > 0 ? 'warning' : 'verified' }}</mat-icon>
        </div>
        <div class="kpi-body">
          <div class="kpi-value" [class.kpi-value-error]="errorCount > 0">{{ errorCount }}</div>
          <div class="kpi-label">Errors</div>
        </div>
      </div>
    </div>

    <div *ngIf="loading" class="loading-center">
      <mat-spinner diameter="36"></mat-spinner>
    </div>

    <div *ngIf="!loading" class="content-row">
      <!-- Active syncs -->
      <section class="panel">
        <div class="panel-header">
          <h2 class="panel-title">Syncs</h2>
          <a mat-button routerLink="/syncs" class="panel-link">View all</a>
        </div>

        <div *ngIf="syncs.length === 0" class="panel-empty">
          <mat-icon>sync</mat-icon>
          <p>No syncs configured yet.</p>
          <a mat-stroked-button routerLink="/syncs/new">Create one</a>
        </div>

        <div class="sync-list" *ngIf="syncs.length > 0">
          <a class="sync-row" *ngFor="let s of syncs" [routerLink]="['/syncs', s.id]">
            <span class="sync-dot"
                  [class.dot-active]="s.is_active"
                  [class.dot-inactive]="!s.is_active"></span>
            <div class="sync-info">
              <span class="sync-name">{{ s.name }}</span>
              <span class="sync-meta">{{ s.adapter_id }} → {{ s.connector_id }}</span>
            </div>
            <app-cron-display [expression]="s.cron_expression"></app-cron-display>
            <mat-icon class="sync-arrow">chevron_right</mat-icon>
          </a>
        </div>
      </section>

      <!-- Recent runs -->
      <section class="panel">
        <div class="panel-header">
          <h2 class="panel-title">Recent Syncs</h2>
          <a mat-button routerLink="/runs" class="panel-link">View all</a>
        </div>

        <div *ngIf="recentRuns.length === 0" class="panel-empty">
          <mat-icon>history</mat-icon>
          <p>No syncs yet. Trigger a sync to see results here.</p>
        </div>

        <div class="run-list" *ngIf="recentRuns.length > 0">
          <div class="run-row" *ngFor="let r of recentRuns">
            <app-status-badge [status]="r.status"></app-status-badge>
            <div class="run-info">
              <span class="run-sync-name">{{ syncName(r.sync_id) }}</span>
              <span class="run-time">{{ r.started_at | localDate:'MMM d, h:mm a' }}</span>
            </div>
            <div class="run-counts" *ngIf="r.changed_count != null">
              <span class="run-count">{{ r.changed_count }} changed</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  `,
  styles: [`
    .page-banner {
      background: linear-gradient(135deg, #011627 0%, #0d2137 100%);
      border-bottom: 1px solid rgba(255,255,255,0.06);
      padding: 0 28px;
      margin: -20px -24px 0;
    }
    .banner-inner {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 24px 0;
    }
    .banner-title {
      font-size: 22px;
      font-weight: 700;
      color: #fff;
      margin: 0 0 4px;
    }
    .banner-subtitle {
      font-size: 13px;
      color: rgba(255,255,255,0.5);
      margin: 0;
    }
    .create-btn {
      background: #79ECDD !important;
      color: #011627 !important;
      font-weight: 600;
      border-radius: 4px;
      padding: 0 18px;
      height: 38px;
      font-size: 13px;
    }

    /* KPI grid */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 0;
      background: #fff;
      border-bottom: 1px solid #dee2ec;
      margin: 0 -24px;
    }
    .kpi-tile {
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 16px 24px;
      border-right: 1px solid #dee2ec;
      transition: background 0.12s;
    }
    .kpi-tile:last-child { border-right: none; }
    .kpi-tile:hover { background: #f8f9fb; }
    .kpi-tile-alert { background: rgba(222,53,11,0.03); }
    .kpi-icon-wrap {
      width: 40px; height: 40px; border-radius: 8px;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0;
    }
    .kpi-icon-wrap mat-icon { font-size: 20px; width: 20px; height: 20px; }
    .kpi-total { background: rgba(1,22,39,0.07); }
    .kpi-total mat-icon { color: #5a6070; }
    .kpi-active { background: rgba(0,166,80,0.1); }
    .kpi-active mat-icon { color: #00a650; }
    .kpi-runs { background: rgba(0,82,204,0.1); }
    .kpi-runs mat-icon { color: #0052cc; }
    .kpi-error mat-icon { color: #de350b; }
    .kpi-error { background: rgba(222,53,11,0.1); }
    .kpi-ok { background: rgba(0,166,80,0.1); }
    .kpi-ok mat-icon { color: #00a650; }
    .kpi-body { display: flex; flex-direction: column; }
    .kpi-value {
      font-size: 22px; font-weight: 700; color: #1d1f2b; line-height: 1.1;
    }
    .kpi-value-active { color: #00a650; }
    .kpi-value-error { color: #de350b; }
    .kpi-label {
      font-size: 11px; font-weight: 600; color: #5e6e82;
      text-transform: uppercase; letter-spacing: 0.4px; margin-top: 2px;
    }

    /* Content layout */
    .loading-center { display: flex; justify-content: center; padding: 60px; }
    .content-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      padding: 20px 0;
    }

    /* Panels */
    .panel {
      background: #fff;
      border: 1px solid #dee2ec;
      border-radius: 4px;
      overflow: hidden;
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 14px 18px;
      border-bottom: 1px solid #f0f2f7;
    }
    .panel-title {
      font-size: 14px; font-weight: 600; color: #1d1f2b; margin: 0;
    }
    .panel-link { font-size: 12px; color: #0052cc; }
    .panel-empty {
      display: flex; flex-direction: column; align-items: center;
      padding: 40px 24px; text-align: center; color: #5e6e82;
    }
    .panel-empty mat-icon { font-size: 36px; width: 36px; height: 36px; margin-bottom: 12px; }
    .panel-empty p { font-size: 13px; margin: 0 0 16px; }

    /* Sync list */
    .sync-list { display: flex; flex-direction: column; }
    .sync-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 18px;
      border-bottom: 1px solid #f0f2f7;
      text-decoration: none;
      color: inherit;
      transition: background 0.1s;
    }
    .sync-row:last-child { border-bottom: none; }
    .sync-row:hover { background: #f8f9fb; }
    .sync-dot {
      width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
    }
    .dot-active { background: #00a650; box-shadow: 0 0 0 2px rgba(0,166,80,0.18); }
    .dot-inactive { background: #c4cad6; }
    .sync-info { flex: 1; display: flex; flex-direction: column; min-width: 0; }
    .sync-name {
      font-size: 13px; font-weight: 600; color: #1d1f2b;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .sync-meta { font-size: 11px; color: #5e6e82; }
    .sync-arrow { color: #c4cad6; font-size: 18px; width: 18px; height: 18px; }

    /* Run list */
    .run-list { display: flex; flex-direction: column; }
    .run-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 18px;
      border-bottom: 1px solid #f0f2f7;
    }
    .run-row:last-child { border-bottom: none; }
    .run-info { flex: 1; display: flex; flex-direction: column; min-width: 0; }
    .run-sync-name {
      font-size: 12px; font-weight: 600; color: #1d1f2b;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .run-time { font-size: 11px; color: #5e6e82; }
    .run-counts { display: flex; gap: 6px; flex-shrink: 0; }
    .run-count { font-size: 11px; color: #5e6e82; }
  `],
})
export class DashboardComponent implements OnInit {
  private destroyRef = inject(DestroyRef);

  syncs: SyncConfig[] = [];
  recentRuns: SyncRun[] = [];
  loading = true;

  get activeCount(): number { return this.syncs.filter(s => s.is_active).length; }
  get errorCount(): number { return this.recentRuns.filter(r => r.status === 'error' || r.status === 'failed').length; }

  syncName(syncId: string): string {
    return this.syncs.find(s => s.id === syncId)?.name ?? syncId;
  }

  constructor(private syncService: SyncService) {}

  ngOnInit() {
    this.syncService.getAll()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: syncs => {
          this.syncs = syncs;
          this._loadRecentRuns(syncs);
        },
        error: () => { this.loading = false; },
      });
  }

  private _loadRecentRuns(syncs: SyncConfig[]) {
    if (syncs.length === 0) { this.loading = false; return; }

    // Load runs from the first 3 syncs for the dashboard summary
    const slice = syncs.slice(0, 3);
    let pending = slice.length;
    const runs: SyncRun[] = [];

    slice.forEach(s => {
      this.syncService.getRuns(s.id, 5)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: r => {
            runs.push(...r);
            if (--pending === 0) {
              this.recentRuns = runs
                .sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))
                .slice(0, 8);
              this.loading = false;
            }
          },
          error: () => {
            if (--pending === 0) { this.loading = false; }
          },
        });
    });
  }
}
