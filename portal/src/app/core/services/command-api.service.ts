import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, map } from 'rxjs';

import {
  CommandLogRecord,
  CommandLogRecordApiResponse,
  CommandResult,
  CommandResultApiResponse,
  CommandType,
  fromRecordApiResponse,
  fromResultApiResponse,
} from '../models/command.model';

@Injectable({ providedIn: 'root' })
export class CommandApiService {
  constructor(private readonly http: HttpClient) {}

  sendCommand(
    chargerId: string,
    tenantId: string,
    commandType: CommandType,
    payload: Record<string, unknown>,
  ): Observable<CommandResult> {
    return this.http
      .post<CommandResultApiResponse>(`/admin/chargers/${chargerId}/commands`, {
        tenant_id: tenantId,
        command_type: commandType,
        payload,
      })
      .pipe(map(fromResultApiResponse));
  }

  listRecent(chargerId: string, limit = 20): Observable<CommandLogRecord[]> {
    const params = new HttpParams().set('limit', limit);
    return this.http
      .get<CommandLogRecordApiResponse[]>(`/admin/chargers/${chargerId}/commands`, { params })
      .pipe(map((records) => records.map(fromRecordApiResponse)));
  }
}
