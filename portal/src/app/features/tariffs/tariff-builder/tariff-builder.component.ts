import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';

import { SampleSession, TariffComponentForm, TariffComponentType } from '../../../core/models/tariff.model';
import { TariffApiService } from '../../../core/services/tariff-api.service';
import { allStepSizesValid, calculateSessionCost, hasEnergyOrTimeComponent } from '../tariff-calculator';

@Component({
  selector: 'app-tariff-builder',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './tariff-builder.component.html',
  styleUrl: './tariff-builder.component.scss',
})
export class TariffBuilderComponent {
  readonly form: FormGroup;
  savedTariffId: string | null = null;
  saveError: string | null = null;

  sampleSession: SampleSession = { durationMinutes: 30, kwh: 15, idleMinutes: 0 };

  constructor(
    private readonly fb: FormBuilder,
    private readonly tariffApi: TariffApiService,
  ) {
    this.form = this.fb.group({
      tenantId: ['', Validators.required],
      name: ['', Validators.required],
      components: this.fb.array([this.buildComponentGroup('energy')]),
    });
  }

  get components(): FormArray {
    return this.form.get('components') as FormArray;
  }

  buildComponentGroup(type: TariffComponentType): FormGroup {
    return this.fb.group({
      type: [type, Validators.required],
      priceMinorUnits: [0, [Validators.required, Validators.min(0)]],
      stepSize: [1, [Validators.required, Validators.min(1)]],
      appliesAfterMinutes: [null],
    });
  }

  addComponent(type: TariffComponentType): void {
    this.components.push(this.buildComponentGroup(type));
  }

  removeComponent(index: number): void {
    this.components.removeAt(index);
  }

  get componentValues(): TariffComponentForm[] {
    return this.components.value as TariffComponentForm[];
  }

  get hasRequiredComponent(): boolean {
    return hasEnergyOrTimeComponent(this.componentValues);
  }

  get hasValidStepSizes(): boolean {
    return allStepSizesValid(this.componentValues);
  }

  get canSave(): boolean {
    return this.form.valid && this.hasRequiredComponent && this.hasValidStepSizes;
  }

  get previewTotalMinorUnits(): number | null {
    if (!this.hasValidStepSizes) {
      return null;
    }
    try {
      return calculateSessionCost(this.componentValues, this.sampleSession);
    } catch {
      return null;
    }
  }

  save(): void {
    this.saveError = null;
    if (!this.canSave) {
      this.saveError = this.hasRequiredComponent
        ? 'Every component must have a step size greater than 0.'
        : 'At least one energy or time component is required.';
      return;
    }

    const { tenantId, name } = this.form.value;
    this.tariffApi.create(tenantId, name, this.componentValues).subscribe({
      next: (tariff) => (this.savedTariffId = tariff.id),
      error: () => (this.saveError = 'Failed to save tariff.'),
    });
  }
}
