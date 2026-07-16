import { Component, OnInit, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { HopConfirmDialogComponent } from '@heretto/hop-ui';
import { SyncService, SyncConfig } from '../../core/services/sync.service';
import { NotificationService } from '../../core/services/notification.service';
import { CronDisplayComponent } from '../../shared/components/cron-display/cron-display.component';

@Component({
  selector: 'app-sync-list',
  imports: [
    CommonModule, FormsModule, RouterModule, MatButtonModule, MatIconModule,
    MatDialogModule, MatProgressSpinnerModule, MatTooltipModule,
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
            <span class="bc-current">Syncs</span>
          </nav>
          <h1 class="banner-title">Sync Configurations</h1>
          <p class="banner-subtitle">Manage automated DITA-to-knowledge-base sync jobs.</p>
        </div>
        <div class="banner-right">
          <a mat-flat-button class="create-btn" routerLink="new">
            <mat-icon>add</mat-icon> New Sync
          </a>
        </div>
      </div>
    </div>

    <!-- KPI bar -->
    <div class="metrics-bar">
      <div class="metric-tile">
        <div class="metric-icon-wrap metric-icon-total"><mat-icon>sync</mat-icon></div>
        <div class="metric-body">
          <div class="metric-value">{{ syncs.length }}</div>
          <div class="metric-label">Total</div>
        </div>
      </div>
      <div class="metric-tile">
        <div class="metric-icon-wrap metric-icon-active"><mat-icon>check_circle</mat-icon></div>
        <div class="metric-body">
          <div class="metric-value metric-value-active">{{ activeCount }}</div>
          <div class="metric-label">Active</div>
        </div>
      </div>
      <div class="metric-tile">
        <div class="metric-icon-wrap metric-icon-paused"><mat-icon>pause_circle</mat-icon></div>
        <div class="metric-body">
          <div class="metric-value">{{ inactiveCount }}</div>
          <div class="metric-label">Inactive</div>
        </div>
      </div>
    </div>

    <!-- Filter toolbar -->
    <div class="filter-bar">
      <div class="search-wrap">
        <mat-icon class="search-icon">search</mat-icon>
        <input class="search-input" type="text" placeholder="Search syncs..."
               [(ngModel)]="searchQuery" aria-label="Search syncs">
        <button *ngIf="searchQuery" class="search-clear" (click)="searchQuery = ''" aria-label="Clear search">
          <mat-icon>close</mat-icon>
        </button>
      </div>
      <div class="filter-tabs" role="tablist">
        <button role="tab" class="filter-tab" [class.filter-tab-active]="activeFilter === 'all'"
                (click)="activeFilter = 'all'">
          All <span class="tab-count">{{ syncs.length }}</span>
        </button>
        <button role="tab" class="filter-tab" [class.filter-tab-active]="activeFilter === 'active'"
                (click)="activeFilter = 'active'">
          Active <span class="tab-count">{{ activeCount }}</span>
        </button>
        <button role="tab" class="filter-tab" [class.filter-tab-active]="activeFilter === 'inactive'"
                (click)="activeFilter = 'inactive'">
          Inactive <span class="tab-count">{{ inactiveCount }}</span>
        </button>
      </div>
      <div class="filter-bar-right">
        <span class="results-count">{{ filteredSyncs.length }} record{{ filteredSyncs.length !== 1 ? 's' : '' }}</span>
      </div>
    </div>

    <!-- Loading -->
    <div *ngIf="loading" class="loading-center">
      <mat-spinner diameter="36"></mat-spinner>
    </div>

    <!-- Empty state -->
    <div *ngIf="!loading && syncs.length === 0" class="empty-state">
      <div class="empty-icon-wrap"><mat-icon>sync</mat-icon></div>
      <h2>No syncs configured</h2>
      <p>Create your first sync to start syndicating content to your knowledge base.</p>
      <a mat-flat-button color="primary" routerLink="new">
        <mat-icon>add</mat-icon> Create a Sync
      </a>
    </div>

    <!-- No results -->
    <div *ngIf="!loading && syncs.length > 0 && filteredSyncs.length === 0" class="empty-state">
      <div class="empty-icon-wrap"><mat-icon>search_off</mat-icon></div>
      <h2>No matching syncs</h2>
      <p>Try adjusting your search or filter.</p>
      <button mat-stroked-button (click)="clearFilters()">Clear filters</button>
    </div>

    <!-- Card grid -->
    <div *ngIf="!loading && filteredSyncs.length > 0" class="card-grid">
      <article class="sync-card" *ngFor="let s of filteredSyncs"
               (click)="openDetail(s)" role="button" tabindex="0"
               (keydown.enter)="openDetail(s)" (keydown.space)="openDetail(s)"
               [attr.aria-label]="'Open sync: ' + s.name">

        <div class="card-status-bar"
             [class.bar-active]="s.is_active"
             [class.bar-inactive]="!s.is_active"></div>

        <div class="card-inner">
          <div class="card-header">
            <div class="card-dot"
                 [class.dot-active]="s.is_active"
                 [class.dot-inactive]="!s.is_active"></div>
            <div class="card-name-wrap">
              <h3 class="card-name" [title]="s.name">{{ s.name }}</h3>
              <span class="card-pipeline">{{ s.adapter_id }} → {{ s.connector_id }}</span>
            </div>
            <span class="card-pill"
                  [class.pill-active]="s.is_active"
                  [class.pill-inactive]="!s.is_active">
              {{ s.is_active ? 'Active' : 'Inactive' }}
            </span>
          </div>

          <div class="card-cron-row">
            <mat-icon class="card-field-icon">schedule</mat-icon>
            <app-cron-display [expression]="s.cron_expression"></app-cron-display>
          </div>

          <div class="card-tags">
            <span class="tag tag-org">
              <mat-icon>business</mat-icon> {{ s.org_id }}
            </span>
            <span *ngIf="s.deployment_id" class="tag tag-deploy">
              <mat-icon>cloud_upload</mat-icon> {{ s.deployment_id }}
            </span>
          </div>

          <div class="card-footer">
            <div class="card-meta">
              <span *ngIf="s.created_at" class="meta-text">
                Created {{ s.created_at | date:'MMM d, yyyy' }}
              </span>
              <span *ngIf="s.high_water_mark" class="meta-text">
                Last sync: {{ s.high_water_mark | date:'MMM d, h:mm a' }}
              </span>
            </div>
            <div class="card-actions" (click)="$event.stopPropagation()">
              <button mat-icon-button class="action-btn" (click)="triggerNow(s)"
                      matTooltip="Run now">
                <mat-icon>play_arrow</mat-icon>
              </button>
              <a mat-icon-button class="action-btn" [routerLink]="[s.id, 'edit']"
                 matTooltip="Edit">
                <mat-icon>edit</mat-icon>
              </a>
              <button mat-icon-button class="action-btn action-btn-danger" (click)="deleteSync(s)"
                      matTooltip="Deactivate">
                <mat-icon>delete</mat-icon>
              </button>
            </div>
          </div>
        </div>
      </article>
    </div>
  `,
  styles: [`
    .page-banner {
      background: linear-gradient(135deg, #011627 0%, #0d2137 100%);
      border-bottom: 1px solid rgba(255,255,255,0.06);
      padding: 0 28px;
      margin: -20px -24px 0;
    }
    .banner-inner { display: flex; justify-content: space-between; align-items: center; padding: 24px 0; }
    .breadcrumb { display: flex; align-items: center; gap: 4px; margin-bottom: 8px; }
    .bc-link { font-size: 12px; color: rgba(255,255,255,0.5); text-decoration: none; transition: color 0.1s; }
    .bc-link:hover { color: #79ECDD; }
    .bc-sep { font-size: 14px; width: 14px; height: 14px; color: rgba(255,255,255,0.3); }
    .bc-current { font-size: 12px; color: rgba(255,255,255,0.55); }
    .banner-title { font-size: 22px; font-weight: 700; color: #fff; margin: 0 0 4px; }
    .banner-subtitle { font-size: 13px; color: rgba(255,255,255,0.5); margin: 0; }
    .create-btn { background: #79ECDD !important; color: #011627 !important; font-weight: 600; border-radius: 4px; padding: 0 18px; height: 38px; font-size: 13px; }

    .metrics-bar { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0; background: #fff; border-bottom: 1px solid #dee2ec; margin: 0 -24px; }
    .metric-tile { display: flex; align-items: center; gap: 14px; padding: 16px 24px; border-right: 1px solid #dee2ec; }
    .metric-tile:last-child { border-right: none; }
    .metric-icon-wrap { width: 40px; height: 40px; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
    .metric-icon-wrap mat-icon { font-size: 20px; width: 20px; height: 20px; }
    .metric-icon-total { background: rgba(1,22,39,0.07); }
    .metric-icon-total mat-icon { color: #5a6070; }
    .metric-icon-active { background: rgba(0,166,80,0.1); }
    .metric-icon-active mat-icon { color: #00a650; }
    .metric-icon-paused { background: rgba(151,160,175,0.15); }
    .metric-icon-paused mat-icon { color: #5e6e82; }
    .metric-body { display: flex; flex-direction: column; }
    .metric-value { font-size: 22px; font-weight: 700; color: #1d1f2b; line-height: 1.1; }
    .metric-value-active { color: #00a650; }
    .metric-label { font-size: 11px; font-weight: 600; color: #5e6e82; text-transform: uppercase; letter-spacing: 0.4px; margin-top: 2px; }

    .filter-bar { display: flex; align-items: center; gap: 16px; padding: 10px 28px; background: #fff; border-bottom: 1px solid #dee2ec; margin: 0 -24px; }
    .search-wrap { display: flex; align-items: center; gap: 6px; background: #f4f5f7; border: 1px solid #dee2ec; border-radius: 4px; padding: 0 10px; height: 34px; width: 260px; flex-shrink: 0; }
    .search-icon { font-size: 16px; width: 16px; height: 16px; color: #5e6e82; }
    .search-input { border: none; background: transparent; outline: none; font-size: 13px; color: #1d1f2b; width: 100%; font-family: inherit; }
    .search-input::placeholder { color: #5e6e82; }
    .search-clear { background: none; border: none; cursor: pointer; padding: 0; display: flex; color: #5e6e82; }
    .search-clear mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .filter-tabs { display: flex; gap: 2px; background: #f4f5f7; border: 1px solid #dee2ec; border-radius: 4px; padding: 3px; }
    .filter-tab { border: none; background: transparent; padding: 4px 12px; border-radius: 3px; font-size: 12.5px; font-weight: 500; color: #5a6070; cursor: pointer; display: flex; align-items: center; gap: 5px; transition: all 0.12s; font-family: inherit; }
    .filter-tab-active { background: #fff !important; color: #011627 !important; font-weight: 600; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .tab-count { background: #e8eaf0; color: #5a6070; border-radius: 10px; padding: 1px 6px; font-size: 11px; font-weight: 600; }
    .filter-tab-active .tab-count { background: rgba(1,22,39,0.08); color: #011627; }
    .filter-bar-right { margin-left: auto; }
    .results-count { font-size: 12px; color: #5e6e82; }

    .loading-center { display: flex; justify-content: center; padding: 60px; }
    .empty-state { display: flex; flex-direction: column; align-items: center; padding: 80px 24px; text-align: center; }
    .empty-icon-wrap { width: 64px; height: 64px; border-radius: 50%; background: #f0f2f7; display: flex; align-items: center; justify-content: center; margin-bottom: 20px; }
    .empty-icon-wrap mat-icon { font-size: 30px; width: 30px; height: 30px; color: #5e6e82; }
    .empty-state h2 { font-size: 16px; color: #3d4460; margin: 0 0 8px; font-weight: 600; }
    .empty-state p { color: #5e6e82; font-size: 13.5px; margin: 0 0 24px; }

    .card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; padding: 20px 0; }

    .sync-card { background: #fff; border: 1px solid #dee2ec; border-radius: 4px; display: flex; cursor: pointer; transition: box-shadow 0.15s, border-color 0.15s, transform 0.12s; overflow: hidden; }
    .sync-card:hover { border-color: #b8c0d0; box-shadow: 0 4px 16px rgba(0,65,117,0.12); transform: translateY(-1px); }
    .sync-card:focus-visible { outline: 2px solid #79ECDD; outline-offset: 2px; }

    .card-status-bar { width: 4px; flex-shrink: 0; }
    .bar-active { background: #00a650; }
    .bar-inactive { background: #c4cad6; }

    .card-inner { flex: 1; padding: 14px 16px 10px; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
    .card-header { display: flex; align-items: flex-start; gap: 8px; }
    .card-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 5px; }
    .dot-active { background: #00a650; box-shadow: 0 0 0 2px rgba(0,166,80,0.18); }
    .dot-inactive { background: #c4cad6; }
    .card-name-wrap { flex: 1; min-width: 0; }
    .card-name { font-size: 14px; font-weight: 600; color: #1d1f2b; margin: 0 0 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .card-pipeline { font-size: 12px; color: #5e6e82; }
    .card-pill { font-size: 10.5px; font-weight: 700; padding: 2px 8px; border-radius: 3px; flex-shrink: 0; text-transform: uppercase; letter-spacing: 0.5px; }
    .pill-active { background: rgba(0,166,80,0.1); color: #006b34; }
    .pill-inactive { background: #f0f2f7; color: #5e6e82; }

    .card-cron-row { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: #5a6070; }
    .card-field-icon { font-size: 14px; width: 14px; height: 14px; color: #5e6e82; flex-shrink: 0; }

    .card-tags { display: flex; flex-wrap: wrap; gap: 5px; }
    .tag { display: inline-flex; align-items: center; gap: 3px; font-size: 11px; font-weight: 500; padding: 2px 7px; border-radius: 3px; white-space: nowrap; }
    .tag mat-icon { font-size: 11px; width: 11px; height: 11px; }
    .tag-org { background: #eef1f8; color: #4a5270; }
    .tag-deploy { background: #f3f0ff; color: #5a34a0; }

    .card-footer { display: flex; justify-content: space-between; align-items: flex-end; border-top: 1px solid #f0f2f7; padding-top: 8px; margin-top: 2px; }
    .card-meta { display: flex; flex-direction: column; gap: 2px; }
    .meta-text { font-size: 11px; color: #5e6e82; }
    .card-actions { display: flex; }
    .action-btn { color: #5e6e82 !important; }
    .action-btn:hover { color: #011627 !important; }
    .action-btn-danger:hover { color: #de350b !important; }
  `],
})
export class SyncListComponent implements OnInit {
  private destroyRef = inject(DestroyRef);

  syncs: SyncConfig[] = [];
  loading = true;
  activeFilter: 'all' | 'active' | 'inactive' = 'all';
  searchQuery = '';

  get activeCount(): number { return this.syncs.filter(s => s.is_active).length; }
  get inactiveCount(): number { return this.syncs.filter(s => !s.is_active).length; }

  get filteredSyncs(): SyncConfig[] {
    let result = this.syncs;
    if (this.activeFilter === 'active') result = result.filter(s => s.is_active);
    if (this.activeFilter === 'inactive') result = result.filter(s => !s.is_active);
    if (this.searchQuery.trim()) {
      const q = this.searchQuery.toLowerCase();
      result = result.filter(s =>
        s.name.toLowerCase().includes(q) ||
        s.adapter_id.toLowerCase().includes(q) ||
        s.connector_id.toLowerCase().includes(q)
      );
    }
    return result;
  }

  clearFilters() { this.searchQuery = ''; this.activeFilter = 'all'; }

  constructor(
    private syncService: SyncService,
    private notifications: NotificationService,
    private dialog: MatDialog,
    private router: Router,
  ) {}

  ngOnInit() { this.loadSyncs(); }

  loadSyncs() {
    this.loading = true;
    this.syncService.getAll()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: s => { this.syncs = s; this.loading = false; },
        error: () => { this.loading = false; },
      });
  }

  openDetail(sync: SyncConfig) {
    this.router.navigate(['/syncs', sync.id]);
  }

  triggerNow(sync: SyncConfig) {
    this.syncService.trigger(sync.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({ next: () => this.notifications.success('Sync triggered successfully') });
  }

  deleteSync(sync: SyncConfig) {
    const ref = this.dialog.open(HopConfirmDialogComponent, {
      data: {
        title: 'Deactivate Sync',
        message: `Deactivate "${sync.name}"? This will stop all scheduled runs for this sync.`,
        confirmText: 'Deactivate',
      },
    });
    ref.afterClosed()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(confirmed => {
        if (confirmed) {
          this.syncService.delete(sync.id)
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({ next: () => { this.notifications.success('Sync deactivated'); this.loadSyncs(); } });
        }
      });
  }
}
