import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { ApiService } from './api.service';

export interface Credential {
  id: string;
  type: string;
  name: string;
  created_at: string;
  updated_at: string | null;
}

export interface CredentialCreate {
  type: string;
  name: string;
  credentials: Record<string, string>;
}

@Injectable({ providedIn: 'root' })
export class CredentialService {
  private api = inject(ApiService);

  list(type?: string): Observable<Credential[]> {
    return this.api.get<Credential[]>('/credentials').pipe(
      map(creds => type ? creds.filter(c => c.type === type) : creds),
    );
  }

  create(data: CredentialCreate): Observable<Credential> {
    return this.api.post<Credential>('/credentials', data);
  }
}
