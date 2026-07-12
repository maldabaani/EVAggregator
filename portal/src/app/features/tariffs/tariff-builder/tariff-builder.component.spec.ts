import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { TariffBuilderComponent } from './tariff-builder.component';

describe('TariffBuilderComponent', () => {
  let fixture: ComponentFixture<TariffBuilderComponent>;
  let component: TariffBuilderComponent;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TariffBuilderComponent, HttpClientTestingModule],
    }).compileComponents();

    fixture = TestBed.createComponent(TariffBuilderComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  afterEach(() => httpMock.verify());

  it('the live preview reflects the correct total for the sample session as the admin edits', () => {
    component.components.at(0).patchValue({ type: 'energy', priceMinorUnits: 150, stepSize: 1 });
    component.addComponent('flat');
    component.components.at(1).patchValue({ priceMinorUnits: 200, stepSize: 1 });
    fixture.detectChanges();

    expect(component.previewTotalMinorUnits).toBe(15 * 150 + 200);

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.querySelector('[data-testid="preview-total"]')?.textContent).toContain(
      String(15 * 150 + 200),
    );
  });

  it('blocks save when the tariff has no energy or time component', () => {
    component.components.clear();
    component.addComponent('flat');
    component.components.at(0).patchValue({ priceMinorUnits: 200, stepSize: 1 });
    component.form.patchValue({ tenantId: 't-1', name: 'Flat only' });
    fixture.detectChanges();

    component.save();
    fixture.detectChanges();

    expect(component.canSave).toBeFalse();
    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.querySelector('[data-testid="save-button"]')?.hasAttribute('disabled')).toBeTrue();
    expect(compiled.querySelector('[data-testid="missing-component-error"]')).toBeTruthy();
    httpMock.expectNone('/admin/tariffs');
  });

  it('shows $0 idle cost in the preview for a session shorter than the grace period', () => {
    component.components.clear();
    component.addComponent('energy');
    component.components.at(0).patchValue({ priceMinorUnits: 150, stepSize: 1 });
    component.addComponent('idle');
    component.components.at(1).patchValue({ priceMinorUnits: 50, stepSize: 1, appliesAfterMinutes: 10 });
    component.sampleSession = { durationMinutes: 30, kwh: 15, idleMinutes: 5 };
    fixture.detectChanges();

    expect(component.previewTotalMinorUnits).toBe(15 * 150); // idle contributes nothing
  });

  it('saving a valid tariff posts to the API and shows the saved confirmation', () => {
    component.components.at(0).patchValue({ type: 'energy', priceMinorUnits: 150, stepSize: 1 });
    component.form.patchValue({ tenantId: 't-1', name: 'Standard' });
    fixture.detectChanges();

    component.save();

    const req = httpMock.expectOne('/admin/tariffs');
    expect(req.request.body.name).toBe('Standard');
    req.flush({ id: 'tariff-1', name: 'Standard', currency: 'AED' });
    fixture.detectChanges();

    expect(component.savedTariffId).toBe('tariff-1');
    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.querySelector('[data-testid="saved-confirmation"]')?.textContent).toContain('tariff-1');
  });

  it('removing a component updates the preview', () => {
    component.addComponent('flat');
    component.components.at(0).patchValue({ type: 'energy', priceMinorUnits: 150, stepSize: 1 });
    component.components.at(1).patchValue({ priceMinorUnits: 500, stepSize: 1 });
    fixture.detectChanges();
    expect(component.previewTotalMinorUnits).toBe(15 * 150 + 500);

    component.removeComponent(1);
    fixture.detectChanges();

    expect(component.previewTotalMinorUnits).toBe(15 * 150);
  });
});
