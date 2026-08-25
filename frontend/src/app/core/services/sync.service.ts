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
  mapping: Record<string, unknown>;
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
  deployment_id: string;
  cron_expression: string;
  mapping?: Record<string, unknown>;
  credential_id?: string;
}

export interface UpdateSyncInput {
  name?: string;
  cron_expression?: string;
  deployment_id?: string;
  credential_id?: string;
  mapping?: Record<string, unknown>;
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

  update(id: string, input: UpdateSyncInput): Observable<SyncConfig> {
    return this.api.put<SyncConfig>(`/syncs/${id}`, input);
  }

  delete(id: string): Observable<void> {
    return this.api.delete(`/syncs/${id}`);
  }

  trigger(id: string, forceFull = false): Observable<{ sync_id: string; message: string }> {
    const params = forceFull ? { force_full: 'true' } : undefined;
    return this.api.post(`/syncs/${id}/trigger`, {}, params);
  }

  getRuns(syncId: string, limit = 20): Observable<SyncRun[]> {
    return this.api.get<SyncRun[]>(`/syncs/${syncId}/runs`, { limit: String(limit) });
  }
}
