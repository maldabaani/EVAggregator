import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

import { TariffComponentForm } from '../models/tariff.model';
import { devTenantHeaders } from './dev-tenant-header';

export interface SavedTariff {
  id: string;
  name: string;
  currency: string;
}

@Injectable({ providedIn: 'root' })
export class TariffApiService {
  private readonly baseUrl = '/admin/tariffs';

  constructor(private readonly http: HttpClient) {}

  list(tenantId: string): Observable<SavedTariff[]> {
    return this.http
      .get<{ data: SavedTariff[] }>(this.baseUrl, {
        params: { tenant_id: tenantId },
        headers: devTenantHeaders(tenantId),
      })
      .pipe(map((response) => response.data));
  }

  create(tenantId: string, name: string, components: TariffComponentForm[]): Observable<SavedTariff> {
    return this.http.post<SavedTariff>(
      this.baseUrl,
      { tenant_id: tenantId, name, components: components.map(toApiComponent) },
      { headers: devTenantHeaders(tenantId) },
    );
  }

  update(tariffId: string, tenantId: string, name: string, components: TariffComponentForm[]): Observable<SavedTariff> {
    return this.http.put<SavedTariff>(
      `${this.baseUrl}/${tariffId}`,
      { name, components: components.map(toApiComponent) },
      { headers: devTenantHeaders(tenantId) },
    );
  }
}

function toApiComponent(component: TariffComponentForm) {
  return {
    type: component.type,
    price_minor_units: component.priceMinorUnits,
    step_size: component.stepSize,
    applies_after_minutes: component.appliesAfterMinutes,
  };
}
