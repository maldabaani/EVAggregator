import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { Partner } from '../../core/models/partner.model';
import { DashboardComponent } from './dashboard.component';

describe('DashboardComponent', () => {
  let fixture: ComponentFixture<DashboardComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DashboardComponent, HttpClientTestingModule],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(DashboardComponent);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('renders a panel linking to each main section', () => {
    fixture.detectChanges();
    httpMock.expectOne('/admin/ocpi/partners').flush({ data: [] });
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.querySelector('[data-testid="panel-/partners"]')).toBeTruthy();
    expect(compiled.querySelector('[data-testid="panel-/tariffs"]')).toBeTruthy();
    expect(compiled.querySelector('[data-testid="panel-/cost-dashboard"]')).toBeTruthy();
    expect(compiled.querySelector('[data-testid="panel-/commands"]')).toBeTruthy();
  });

  it('shows the real partner count and connected count', () => {
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
      {
        id: 'p-2',
        tenant_id: 'tenant-1',
        party_id: 'DEF',
        country_code: 'AE',
        negotiated_version: null,
        status: 'pending',
        last_handshake_at: null,
      },
    ];

    fixture.detectChanges();
    httpMock.expectOne('/admin/ocpi/partners').flush({ data: partners });
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.querySelector('[data-testid="partner-count"]')?.textContent?.trim()).toBe('2');
    expect(compiled.querySelector('[data-testid="connected-count"]')?.textContent?.trim()).toBe('1');
  });
});
