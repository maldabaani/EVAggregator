import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

import { CreatedPartner, Partner, PriceListAttachment, ReconciliationEntry } from '../models/partner.model';

@Injectable({ providedIn: 'root' })
export class PartnerApiService {
  private readonly baseUrl = '/admin/ocpi';

  constructor(private readonly http: HttpClient) {}

  listPartners(): Observable<Partner[]> {
    return this.http
      .get<{ data: Partner[] }>(`${this.baseUrl}/partners`)
      .pipe(map((response) => response.data));
  }

  createPartner(tenantId: string, partyId: string, countryCode: string): Observable<CreatedPartner> {
    return this.http.post<CreatedPartner>(`${this.baseUrl}/partners`, {
      tenant_id: tenantId,
      party_id: partyId,
      country_code: countryCode,
    });
  }

  rotateToken(partnerId: string): Observable<{ token_a: string }> {
    return this.http.post<{ token_a: string }>(`${this.baseUrl}/partners/${partnerId}/rotate-token`, {});
  }

  attachPriceList(partnerId: string, attachment: PriceListAttachment): Observable<void> {
    return this.http.post<void>(`${this.baseUrl}/partners/${partnerId}/price-lists`, attachment);
  }

  getReconciliation(status?: string, from?: string, to?: string): Observable<ReconciliationEntry[]> {
    const params: Record<string, string> = {};
    if (status) params['status'] = status;
    if (from) params['from_'] = from;
    if (to) params['to'] = to;
    return this.http
      .get<{ data: ReconciliationEntry[] }>(`${this.baseUrl}/reconciliation`, { params })
      .pipe(map((response) => response.data));
  }

  reconciliationExportUrl(status?: string): string {
    return status
      ? `${this.baseUrl}/reconciliation/export?status=${encodeURIComponent(status)}`
      : `${this.baseUrl}/reconciliation/export`;
  }
}
