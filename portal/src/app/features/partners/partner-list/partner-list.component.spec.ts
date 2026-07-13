import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { Partner } from '../../../core/models/partner.model';
import { PartnerListComponent } from './partner-list.component';

describe('PartnerListComponent', () => {
  let fixture: ComponentFixture<PartnerListComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PartnerListComponent, HttpClientTestingModule],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(PartnerListComponent);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('renders an empty state with a "Connect a partner" CTA when no partner data exists', () => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/admin/ocpi/partners');
    req.flush({ data: [] });
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    const emptyState = compiled.querySelector('[data-testid="empty-state"]');
    const cta = compiled.querySelector('[data-testid="connect-partner-cta"]');
    const table = compiled.querySelector('[data-testid="partner-table"]');

    expect(emptyState).toBeTruthy();
    expect(cta).toBeTruthy();
    expect(cta?.textContent).toContain('Connect a partner');
    expect(table).toBeFalsy();
  });

  it('renders a table of partners when partner data exists', () => {
    const partners: Partner[] = [
      {
        id: 'p-1',
        tenant_id: 'tenant-1',
        party_id: 'ABC',
        country_code: 'AE',
        negotiated_version: '2.2.1',
        status: 'connected',
        last_handshake_at: '2026-07-01T00:00:00Z',
      },
    ];

    fixture.detectChanges();
    const req = httpMock.expectOne('/admin/ocpi/partners');
    req.flush({ data: partners });
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.querySelector('[data-testid="partner-table"]')).toBeTruthy();
    expect(compiled.querySelector('[data-testid="empty-state"]')).toBeFalsy();
    expect(compiled.textContent).toContain('ABC');
  });

  it('shows a "New partner" link in the header even when partners already exist', () => {
    const partners: Partner[] = [
      {
        id: 'p-1',
        tenant_id: 'tenant-1',
        party_id: 'ABC',
        country_code: 'AE',
        negotiated_version: '2.2.1',
        status: 'connected',
        last_handshake_at: '2026-07-01T00:00:00Z',
      },
    ];

    fixture.detectChanges();
    httpMock.expectOne('/admin/ocpi/partners').flush({ data: partners });
    fixture.detectChanges();

    const link = fixture.nativeElement.querySelector('[data-testid="new-partner-link"]');
    expect(link).toBeTruthy();
    expect(link.getAttribute('href')).toBe('/partners/new');
  });
});
