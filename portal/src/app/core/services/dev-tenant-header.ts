import { HttpHeaders } from '@angular/common/http';

/**
 * Dev-only: identifies the tenant to `evagg-gateway`'s dev-mode request
 * forwarder (`evagg.gateway.dev_forwarder`), which signs it and forwards to
 * `evagg.main`. Stands in for a login flow the portal doesn't have —
 * everywhere this header is used, the operator already typed the tenant id
 * into the same form.
 */
export const DEV_TENANT_HEADER = 'X-Dev-Tenant-Id';

export function devTenantHeaders(tenantId: string): HttpHeaders {
  return new HttpHeaders({ [DEV_TENANT_HEADER]: tenantId });
}
