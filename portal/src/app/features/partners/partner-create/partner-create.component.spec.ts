import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { PartnerCreateComponent } from './partner-create.component';

const TENANT_ID = 'tenant-123';

describe('PartnerCreateComponent', () => {
  let fixture: ComponentFixture<PartnerCreateComponent>;
  let component: PartnerCreateComponent;
  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PartnerCreateComponent, HttpClientTestingModule],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(PartnerCreateComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    fixture.detectChanges();
  });

  afterEach(() => httpMock.verify());

  function compiled(): HTMLElement {
    return fixture.nativeElement;
  }

  it('does not submit when the form is invalid', () => {
    compiled().querySelector<HTMLButtonElement>('[data-testid="create-partner-button"]')!.click();
    fixture.detectChanges();

    expect(component.form.invalid).toBeTrue();
    httpMock.expectNone(() => true);
  });

  it('creates the partner and shows the one-time token', () => {
    component.form.patchValue({ tenantId: TENANT_ID, partyId: 'xyz', countryCode: 'ae' });
    component.save();

    const req = httpMock.expectOne('/admin/ocpi/partners');
    expect(req.request.body).toEqual({ tenant_id: TENANT_ID, party_id: 'XYZ', country_code: 'AE' });
    req.flush({
      id: 'partner-1',
      party_id: 'XYZ',
      country_code: 'AE',
      negotiated_version: null,
      status: 'pending',
      last_handshake_at: null,
      token_a: 'one-time-token',
    });
    fixture.detectChanges();

    expect(compiled().querySelector('[data-testid="partner-created-panel"]')).toBeTruthy();
    expect(compiled().querySelector('[data-testid="created-token-a"]')?.textContent).toContain('one-time-token');
    expect(compiled().querySelector('[data-testid="partner-create-form"]')).toBeFalsy();
  });

  it('shows an error message when creation fails', () => {
    component.form.patchValue({ tenantId: TENANT_ID, partyId: 'XYZ', countryCode: 'AE' });
    component.save();

    httpMock.expectOne('/admin/ocpi/partners').flush('boom', { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();

    expect(compiled().querySelector('[data-testid="save-error"]')).toBeTruthy();
    expect(compiled().querySelector('[data-testid="partner-created-panel"]')).toBeFalsy();
  });

  it('navigates to the new partner detail page when "Go to partner" is clicked', () => {
    const navigateSpy = spyOn(router, 'navigate');
    component.form.patchValue({ tenantId: TENANT_ID, partyId: 'XYZ', countryCode: 'AE' });
    component.save();
    httpMock.expectOne('/admin/ocpi/partners').flush({
      id: 'partner-1',
      party_id: 'XYZ',
      country_code: 'AE',
      negotiated_version: null,
      status: 'pending',
      last_handshake_at: null,
      token_a: 'one-time-token',
    });
    fixture.detectChanges();

    compiled().querySelector<HTMLButtonElement>('[data-testid="go-to-partner-button"]')!.click();

    expect(navigateSpy).toHaveBeenCalledWith(['/partners', 'partner-1']);
  });
});
