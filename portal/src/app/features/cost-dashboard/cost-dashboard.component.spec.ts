import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CostReportApiResponse } from '../../core/models/cost-report.model';
import { CostDashboardComponent } from './cost-dashboard.component';

const TEAM_ID = 'team-123';

function sampleResponse(overrides: Partial<CostReportApiResponse> = {}): CostReportApiResponse {
  return {
    group_by: 'driver',
    rows: [
      { key: 'driver-a', session_count: 3, kwh_total: 40, cost_total_minor_units: 6000 },
      { key: 'driver-b', session_count: 1, kwh_total: 10, cost_total_minor_units: 1500 },
    ],
    total_session_count: 4,
    total_kwh: 50,
    total_cost_minor_units: 7500,
    incomplete_dates: [],
    ...overrides,
  };
}

describe('CostDashboardComponent', () => {
  let fixture: ComponentFixture<CostDashboardComponent>;
  let component: CostDashboardComponent;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CostDashboardComponent, HttpClientTestingModule],
    }).compileComponents();

    fixture = TestBed.createComponent(CostDashboardComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  afterEach(() => httpMock.verify());

  function compiled(): HTMLElement {
    return fixture.nativeElement;
  }

  it('does not fire a request when Team ID is empty', () => {
    compiled().querySelector<HTMLButtonElement>('[data-testid="load-report-button"]')!.click();
    fixture.detectChanges();

    expect(component.form.invalid).toBeTrue();
    httpMock.expectNone(() => true);
  });

  it('shows a loading indicator while the request is in flight, then renders the report', () => {
    component.form.patchValue({ teamId: TEAM_ID });
    component.load();
    fixture.detectChanges();

    expect(compiled().querySelector('[data-testid="loading-state"]')).toBeTruthy();

    const req = httpMock.expectOne((r) => r.url === `/admin/teams/${TEAM_ID}/cost-report`);
    expect(req.request.params.get('group_by')).toBe('driver');
    req.flush(sampleResponse());
    fixture.detectChanges();

    expect(compiled().querySelector('[data-testid="loading-state"]')).toBeFalsy();
    expect(compiled().querySelector('[data-testid="stat-sessions"] .stat-tile__value')?.textContent).toContain('4');
  });

  it('summarizes totals correctly in the stat tiles', () => {
    component.form.patchValue({ teamId: TEAM_ID });
    component.load();
    httpMock.expectOne(() => true).flush(sampleResponse());
    fixture.detectChanges();

    expect(compiled().querySelector('[data-testid="stat-energy"] .stat-tile__value')?.textContent).toContain('50');
    expect(compiled().querySelector('[data-testid="stat-total-cost"] .stat-tile__value')?.textContent).toContain(
      '75.00',
    );
    // 7500 minor units / 4 sessions = 18.75
    expect(compiled().querySelector('[data-testid="stat-avg-cost"] .stat-tile__value')?.textContent).toContain(
      '18.75',
    );
  });

  it('sorts rows by cost descending and scales the meter bar relative to the largest row', () => {
    component.form.patchValue({ teamId: TEAM_ID });
    component.load();
    httpMock.expectOne(() => true).flush(sampleResponse());
    fixture.detectChanges();

    const rows = component.rowViews;
    expect(rows[0].key).toBe('driver-a'); // 6000 > 1500
    expect(rows[0].barPercent).toBe(100);
    expect(rows[1].barPercent).toBe(25); // 1500 / 6000
  });

  it('clicking the site toggle re-fetches with group_by=site once a report is already loaded', () => {
    component.form.patchValue({ teamId: TEAM_ID });
    component.load();
    httpMock.expectOne(() => true).flush(sampleResponse());
    fixture.detectChanges();

    compiled().querySelector<HTMLButtonElement>('[data-testid="group-by-site-button"]')!.click();
    fixture.detectChanges();

    const req = httpMock.expectOne((r) => r.url === `/admin/teams/${TEAM_ID}/cost-report`);
    expect(req.request.params.get('group_by')).toBe('site');
    req.flush(sampleResponse({ group_by: 'site' }));
  });

  it('shows the incomplete-data warning banner only when incomplete_dates is non-empty', () => {
    component.form.patchValue({ teamId: TEAM_ID });
    component.load();
    httpMock.expectOne(() => true).flush(sampleResponse({ incomplete_dates: ['2026-06-01'] }));
    fixture.detectChanges();

    const banner = compiled().querySelector('[data-testid="incomplete-dates-banner"]');
    expect(banner).toBeTruthy();
    expect(banner?.textContent).toContain('2026-06-01');
  });

  it('shows the empty state when the report has no rows', () => {
    component.form.patchValue({ teamId: TEAM_ID });
    component.load();
    httpMock
      .expectOne(() => true)
      .flush(sampleResponse({ rows: [], total_session_count: 0, total_kwh: 0, total_cost_minor_units: 0 }));
    fixture.detectChanges();

    expect(compiled().querySelector('[data-testid="empty-state"]')).toBeTruthy();
    expect(compiled().querySelector('[data-testid="report-table"]')).toBeFalsy();
  });

  it('shows an error state on request failure, and retry re-fetches', () => {
    component.form.patchValue({ teamId: TEAM_ID });
    component.load();
    httpMock.expectOne(() => true).flush('boom', { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();

    expect(compiled().querySelector('[data-testid="error-state"]')).toBeTruthy();

    compiled().querySelector<HTMLButtonElement>('[data-testid="retry-button"]')!.click();
    const retryReq = httpMock.expectOne(() => true);
    retryReq.flush(sampleResponse());
    fixture.detectChanges();

    expect(compiled().querySelector('[data-testid="error-state"]')).toBeFalsy();
  });

  it('the CSV export link points at the csv endpoint with matching filter params', () => {
    component.form.patchValue({ teamId: TEAM_ID, dateFrom: '2026-06-01', dateTo: '2026-06-30' });
    component.load();
    httpMock.expectOne(() => true).flush(sampleResponse());
    fixture.detectChanges();

    const link = compiled().querySelector<HTMLAnchorElement>('[data-testid="export-csv-link"]');
    expect(link?.getAttribute('href')).toContain(`/admin/teams/${TEAM_ID}/cost-report/csv`);
    expect(link?.getAttribute('href')).toContain('date_from=2026-06-01');
    expect(link?.getAttribute('href')).toContain('date_to=2026-06-30');
  });
});
