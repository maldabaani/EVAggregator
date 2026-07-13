import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, map } from 'rxjs';

import { CostReport, CostReportApiResponse, CostReportGroupBy, fromApiResponse } from '../models/cost-report.model';
import { devTenantHeaders } from './dev-tenant-header';

@Injectable({ providedIn: 'root' })
export class CostReportApiService {
  constructor(private readonly http: HttpClient) {}

  getReport(
    teamId: string,
    dateFrom: string,
    dateTo: string,
    groupBy: CostReportGroupBy,
  ): Observable<CostReport> {
    const params = this.buildParams(dateFrom, dateTo, groupBy);
    return this.http
      .get<CostReportApiResponse>(`/admin/teams/${teamId}/cost-report`, { params, headers: devTenantHeaders(teamId) })
      .pipe(map(fromApiResponse));
  }

  csvDownloadUrl(teamId: string, dateFrom: string, dateTo: string, groupBy: CostReportGroupBy): string {
    // A plain download link can't carry a custom header, so the tenant id
    // rides along as a query param instead — see dev_forwarder.py.
    const params = this.buildParams(dateFrom, dateTo, groupBy).set('_dev_tenant_id', teamId);
    return `/admin/teams/${teamId}/cost-report/csv?${params.toString()}`;
  }

  private buildParams(dateFrom: string, dateTo: string, groupBy: CostReportGroupBy): HttpParams {
    return new HttpParams().set('date_from', dateFrom).set('date_to', dateTo).set('group_by', groupBy);
  }
}
