import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';

import { PartnerDetailComponent } from './partner-detail.component';

describe('PartnerDetailComponent', () => {
  let fixture: ComponentFixture<PartnerDetailComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PartnerDetailComponent, HttpClientTestingModule],
      providers: [
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ id: 'partner-1' }) } },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(PartnerDetailComponent);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  function flushInitialReconciliation() {
    const req = httpMock.expectOne((r) => r.url === '/admin/ocpi/reconciliation');
    req.flush({ data: [] });
  }

  it('defaults to the Credentials tab', () => {
    fixture.detectChanges();
    flushInitialReconciliation();

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.querySelector('[data-testid="panel-credentials"]')).toBeTruthy();
    expect(compiled.querySelector('[data-testid="panel-price-lists"]')).toBeFalsy();
  });

  it('switches to the Price Lists tab on click', () => {
    fixture.detectChanges();
    flushInitialReconciliation();

    const button = fixture.nativeElement.querySelector('[data-testid="tab-price-lists"]') as HTMLButtonElement;
    button.click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[data-testid="panel-price-lists"]')).toBeTruthy();
  });

  it('rotating the token invalidates the old one and shows the new token_a', () => {
    fixture.detectChanges();
    flushInitialReconciliation();

    const button = fixture.nativeElement.querySelector('[data-testid="rotate-token-button"]') as HTMLButtonElement;
    button.click();

    const req = httpMock.expectOne('/admin/ocpi/partners/partner-1/rotate-token');
    req.flush({ token_a: 'brand-new-token' });
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[data-testid="rotated-token"]').textContent).toContain(
      'brand-new-token',
    );
  });

  it('attaching a price list posts the form values and resets the form', () => {
    fixture.detectChanges();
    flushInitialReconciliation();

    const component = fixture.componentInstance;
    component.priceListForm = { connectorType: 'Type2', tariffId: 'tariff-1', effectiveFrom: '2026-01-01T00:00' };
    component.attachPriceList();

    const req = httpMock.expectOne('/admin/ocpi/partners/partner-1/price-lists');
    expect(req.request.body.tariffId).toBe('tariff-1');
    req.flush(null);

    expect(component.priceListForm.tariffId).toBe('');
  });

  it('changing the reconciliation status filter reloads entries with that filter', () => {
    fixture.detectChanges();
    flushInitialReconciliation();

    fixture.componentInstance.reconciliationStatusFilter = 'mismatched';
    fixture.componentInstance.loadReconciliation();

    const req = httpMock.expectOne((r) => r.url === '/admin/ocpi/reconciliation' && r.params.get('status') === 'mismatched');
    req.flush({ data: [{ local_cdr_id: 'CDR-1', partner_cdr_uid: 'P-1', status: 'mismatched', delta_fraction: 0.05 }] });
    fixture.detectChanges();

    expect(fixture.componentInstance.reconciliationEntries.length).toBe(1);
  });

  it('exportUrl reflects the current status filter', () => {
    fixture.detectChanges();
    flushInitialReconciliation();

    fixture.componentInstance.reconciliationStatusFilter = 'matched';

    expect(fixture.componentInstance.exportUrl).toContain('status=matched');
  });
});
