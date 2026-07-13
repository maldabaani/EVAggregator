import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { SavedTariff } from '../../../core/services/tariff-api.service';
import { TariffListComponent } from './tariff-list.component';

describe('TariffListComponent', () => {
  let fixture: ComponentFixture<TariffListComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TariffListComponent, HttpClientTestingModule],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(TariffListComponent);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  function typeTenantIdAndLoad(tenantId: string): void {
    const compiled: HTMLElement = fixture.nativeElement;
    const input = compiled.querySelector('[data-testid="tenant-id-input"]') as HTMLInputElement;
    input.value = tenantId;
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    (compiled.querySelector('[data-testid="load-button"]') as HTMLButtonElement).click();
    fixture.detectChanges();
  }

  it('does not fetch until a tenant id is submitted', () => {
    fixture.detectChanges();
    httpMock.expectNone(() => true);
    expect(fixture.componentInstance.tariffs).toBeNull();
  });

  it('shows an empty state when the tenant has no tariffs', () => {
    fixture.detectChanges();
    typeTenantIdAndLoad('tenant-1');

    const req = httpMock.expectOne((r) => r.url === '/admin/tariffs' && r.params.get('tenant_id') === 'tenant-1');
    req.flush({ data: [] });
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.querySelector('[data-testid="empty-state"]')).toBeTruthy();
    expect(compiled.querySelector('[data-testid="tariff-table"]')).toBeFalsy();
  });

  it('renders a table of tariffs when the tenant has some', () => {
    const tariffs: SavedTariff[] = [{ id: 't-1', name: 'Standard', currency: 'AED' }];

    fixture.detectChanges();
    typeTenantIdAndLoad('tenant-1');

    httpMock.expectOne('/admin/tariffs?tenant_id=tenant-1').flush({ data: tariffs });
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.querySelector('[data-testid="tariff-table"]')).toBeTruthy();
    expect(compiled.textContent).toContain('Standard');
  });

  it('shows an error when loading fails', () => {
    fixture.detectChanges();
    typeTenantIdAndLoad('tenant-1');

    httpMock.expectOne((r) => r.url === '/admin/tariffs').flush(
      { detail: 'boom' },
      { status: 500, statusText: 'Server Error' },
    );
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[data-testid="load-error"]')).toBeTruthy();
  });

  it('has a "New tariff" link pointing at the builder', () => {
    fixture.detectChanges();
    const link = fixture.nativeElement.querySelector('[data-testid="new-tariff-link"]');
    expect(link.getAttribute('href')).toBe('/tariffs/new');
  });
});
