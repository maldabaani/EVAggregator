import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { PartnerApiService } from './partner-api.service';

describe('PartnerApiService', () => {
  let service: PartnerApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
    });
    service = TestBed.inject(PartnerApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('listPartners unwraps the data envelope', () => {
    let result: unknown;
    service.listPartners().subscribe((partners) => (result = partners));

    const req = httpMock.expectOne('/admin/ocpi/partners');
    req.flush({ data: [{ id: 'p-1' }] });

    expect(result).toEqual([{ id: 'p-1' }]);
  });

  it('rotateToken posts to the rotate-token endpoint', () => {
    service.rotateToken('p-1').subscribe();

    const req = httpMock.expectOne('/admin/ocpi/partners/p-1/rotate-token');
    expect(req.request.method).toBe('POST');
    req.flush({ token_a: 'new-token' });
  });

  it('attachPriceList posts the attachment payload', () => {
    service
      .attachPriceList('p-1', { connectorType: 'CCS2', tariffId: 't-1', effectiveFrom: '2026-01-01T00:00' })
      .subscribe();

    const req = httpMock.expectOne('/admin/ocpi/partners/p-1/price-lists');
    expect(req.request.method).toBe('POST');
    expect(req.request.body.tariffId).toBe('t-1');
    req.flush(null);
  });

  it('getReconciliation applies status/from/to as query params', () => {
    service.getReconciliation('mismatched', '2026-01-01', '2026-01-31').subscribe();

    const req = httpMock.expectOne(
      (r) => r.url === '/admin/ocpi/reconciliation' && r.params.get('status') === 'mismatched',
    );
    expect(req.request.params.get('from_')).toBe('2026-01-01');
    expect(req.request.params.get('to')).toBe('2026-01-31');
    req.flush({ data: [] });
  });

  it('reconciliationExportUrl includes the status filter when provided', () => {
    expect(service.reconciliationExportUrl('mismatched')).toContain('status=mismatched');
    expect(service.reconciliationExportUrl()).not.toContain('status=');
  });
});
