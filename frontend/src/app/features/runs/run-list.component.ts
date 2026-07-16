import { Component, OnInit, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { SyncService, SyncConfig, SyncRun } from '../../core/services/sync.service';
import { StatusBadgeComponent } from '../../shared/components/status-badge/status-badge.component';

interface RunWithSyncName extends SyncRun {
  syncName: string;
}

@Component({
  selector: 'app-run-list',
  imports: [
    CommonModule, FormsModule, RouterModule, MatButtonModule, MatIconModule,
    MatProgressSpinnerModule, MatSelectModule, MatFormFieldModule,
    StatusBadgeComponent,
  ],
  template: `
    <!-- Page banner -->
    <div class="page-banner">
      <div class="banner-inner">
        <div class="banner-left">
          <nav class="breadcrumb">
            <a routerLink="/dashboard" class="bc-link">Home</a>
            <mat-icon class="bc-sep">chevron_right</mat-icon>
            <span class="bc-current">Run History</span>
          </nav>
          <h1 class="banner-title">Run History</h1>
          <p class="banner-subtitle">Complete history of syndication sync runs across all syncs.</p>
        </div>
      </div>
    </div>

    <!-- Filter bar -->
    <div class="filter-bar">
      <mat-form-field appearance="outline" class="filter-select">
        <mat-label>Filter by sync</mat-label>
        <mat-select [(ngModel)]="selectedSyncId" (ngModelChange)="onFilterChange()">
          <mat-option value="">All syncs</mat-option>
          <mat-option *ngFor="let s of syncs" [value]="s.id">{{ s.name }}</mat-option>
        </mat-select>
      </mat-form-field>
      <div class="filter-tabs" role="tablist">
        <button role="tab" class="filter-tab" [class.filter-tab-active]="statusFilter === ''"
                (click)="statusFilter = ''">
          All <span class="tab-count">{{ allRuns.length }}</span>
        </button>
        <button role="tab" class="filter-tab" [class.filter-tab-active]="statusFilter === 'success'"
                (click)="statusFilter = 'success'">
          Success <span class="tab-count">{{ countByStatus('success') }}</span>
        </button>
        <button role="tab" class="filter-tab" [class.filter-tab-active]="statusFilter === 'error'"
                (click)="statusFilter = 'error'">
          Errors <span class="tab-count">{{ countByStatus('error') }}</span>
        </button>
        <button role="tab" class="filter-tab" [class.filter-tab-active]="statusFilter === 'running'"
                (click)="statusFilter = 'running'">
          Running <span class="tab-count">{{ countByStatus('running') }}</span>
        </button>
      </div>
      <div class="filter-bar-right">
        <span class="results-count">{{ filteredRuns.length }} run{{ filteredRuns.length !== 1 ? 's' : '' }}</span>
      </div>
    </div>

    <div *ngIf="loading" class="loading-center">
      <mat-spinner diameter="36"></mat-spinner>
    </div>

    <div *ngIf="!loading && filteredRuns.length === 0" class="empty-state">
      <div class="empty-icon-wrap"><mat-icon>history</mat-icon></div>
      <h2>No runs found</h2>
      <p>{{ allRuns.length === 0 ? 'No syncs have been run yet.' : 'No runs match the current filter.' }}</p>
    </div>

    <!-- Runs table -->
    <div *ngIf="!loading && filteredRuns.length > 0" class="runs-table-wrap">
      <table class="runs-table">
        <thead>
          <tr>
            <th>Status</th>
            <th>Sync</th>
            <th>Started</th>
            <th>Completed</th>
            <th>Changed</th>
            <th>Removed</th>
            <th>Links Fixed</th>
          </tr>
        </thead>
        <tbody>
          <tr *ngFor="let r of filteredRuns" class="run-tr"
              [routerLink]="['/syncs', r.sync_id]">
            <td><app-status-badge [status]="r.status"></app-status-badge></td>
            <td class="sync-name-cell">
              <a [routerLink]="['/syncs', r.sync_id]" (click)="$event.stopPropagation()" class="sync-link">
                {{ r.syncName }}
              </a>
            </td>
            <td class="time-cell">{{ r.started_at | date:'MMM d, h:mm a' }}</td>
            <td class="time-cell">{{ r.completed_at ? (r.completed_at | date:'h:mm a') : '—' }}</td>
            <td class="num-cell">{{ r.changed_count ?? '—' }}</td>
            <td class="num-cell">{{ r.removed_count ?? '—' }}</td>
            <td class="num-cell">{{ r.links_fixed ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
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

    .filter-bar { display: flex; align-items: center; gap: 16px; padding: 10px 28px; background: #fff; border-bottom: 1px solid #dee2ec; margin: 0 -24px; }
    .filter-select { width: 220px; flex-shrink: 0; }
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
    .empty-state p { color: #5e6e82; font-size: 13.5px; margin: 0; }

    .runs-table-wrap { padding: 20px 0; overflow-x: auto; }
    .runs-table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #dee2ec; border-radius: 4px; overflow: hidden; }
    .runs-table th { padding: 10px 14px; background: #f8f9fb; font-size: 11px; font-weight: 700; color: #5e6e82; text-transform: uppercase; letter-spacing: 0.4px; text-align: left; border-bottom: 1px solid #dee2ec; white-space: nowrap; }
    .runs-table td { padding: 10px 14px; font-size: 13px; color: #1d1f2b; border-bottom: 1px solid #f0f2f7; vertical-align: middle; }
    .run-tr:last-child td { border-bottom: none; }
    .run-tr { cursor: pointer; transition: background 0.1s; }
    .run-tr:hover { background: #f8f9fb; }
    .sync-name-cell { max-width: 200px; }
    .sync-link { color: #0052cc; text-decoration: none; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }
    .sync-link:hover { text-decoration: underline; }
    .time-cell { white-space: nowrap; font-size: 12px; color: #5a6070; }
    .num-cell { text-align: right; font-variant-numeric: tabular-nums; font-size: 12px; }
  `],
})
export class RunListComponent implements OnInit {
  private destroyRef = inject(DestroyRef);

  syncs: SyncConfig[] = [];
  allRuns: RunWithSyncName[] = [];
  loading = true;
  selectedSyncId = '';
  statusFilter = '';

  get filteredRuns(): RunWithSyncName[] {
    let result = this.allRuns;
    if (this.statusFilter) {
      result = result.filter(r => {
        const s = r.status.toLowerCase();
        if (this.statusFilter === 'success') return s === 'success' || s === 'completed';
        if (this.statusFilter === 'error') return s === 'error' || s === 'failed';
        if (this.statusFilter === 'running') return s === 'running' || s === 'in_progress';
        return true;
      });
    }
    return result;
  }

  countByStatus(filter: string): number {
    return this.allRuns.filter(r => {
      const s = r.status.toLowerCase();
      if (filter === 'success') return s === 'success' || s === 'completed';
      if (filter === 'error') return s === 'error' || s === 'failed';
      if (filter === 'running') return s === 'running' || s === 'in_progress';
      return true;
    }).length;
  }

  constructor(private syncService: SyncService) {}

  ngOnInit() { this.loadAll(); }

  loadAll() {
    this.loading = true;
    this.syncService.getAll()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: syncs => {
          this.syncs = syncs;
          this._loadRunsForSyncs(syncs);
        },
        error: () => { this.loading = false; },
      });
  }

  onFilterChange() {
    if (this.selectedSyncId) {
      this.loading = true;
      this.syncService.getRuns(this.selectedSyncId, 50)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: runs => {
            this.allRuns = runs.map(r => ({ ...r, syncName: this._syncName(r.sync_id) }));
            this.loading = false;
          },
          error: () => { this.loading = false; },
        });
    } else {
      this._loadRunsForSyncs(this.syncs);
    }
  }

  private _loadRunsForSyncs(syncs: SyncConfig[]) {
    if (syncs.length === 0) { this.allRuns = []; this.loading = false; return; }
    let pending = syncs.length;
    const collected: RunWithSyncName[] = [];

    syncs.forEach(s => {
      this.syncService.getRuns(s.id, 20)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: runs => {
            collected.push(...runs.map(r => ({ ...r, syncName: s.name })));
            if (--pending === 0) {
              this.allRuns = collected.sort((a, b) =>
                (b.started_at ?? '').localeCompare(a.started_at ?? '')
              );
              this.loading = false;
            }
          },
          error: () => {
            if (--pending === 0) { this.loading = false; }
          },
        });
    });
  }

  private _syncName(id: string): string {
    return this.syncs.find(s => s.id === id)?.name ?? id;
  }
}
