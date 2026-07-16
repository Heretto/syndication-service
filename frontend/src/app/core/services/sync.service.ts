import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface SyncConfig {
  id: string;
  name: string;
  adapter_id: string;
  connector_id: string;
  org_id: string;
  deployment_id: string | null;
  cron_expression: string;
  is_active: boolean;
  high_water_mark: string | null;
  credential_id: string | null;
  created_at: string | null;
}

export interface SyncRun {
  id: string;
  sync_id: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  changed_count: number | null;
  removed_count: number | null;
  links_fixed: number | null;
  error_message: string | null;
}

export interface CreateSyncInput {
  name: string;
  adapter_id: string;
  connector_id: string;
  org_id: string;
  deployment_id: string;
  cron_expression: string;
  mapping?: Record<string, string>;
  credential_id?: string;
}

@Injectable({ providedIn: 'root' })
export class SyncService {
  constructor(private api: ApiService) {}

  getAll(): Observable<SyncConfig[]> {
    return this.api.get<SyncConfig[]>('/syncs');
  }

  getById(id: string): Observable<SyncConfig> {
    return this.api.get<SyncConfig>(`/syncs/${id}`);
  }

  create(input: CreateSyncInput): Observable<SyncConfig> {
    return this.api.post<SyncConfig>('/syncs', input);
  }

  delete(id: string): Observable<void> {
    return this.api.delete(`/syncs/${id}`);
  }

  trigger(id: string): Observable<{ sync_id: string; message: string }> {
    return this.api.post(`/syncs/${id}/trigger`, {});
  }

  getRuns(syncId: string, limit = 20): Observable<SyncRun[]> {
    return this.api.get<SyncRun[]>(`/syncs/${syncId}/runs`, { limit: String(limit) });
  }
}
