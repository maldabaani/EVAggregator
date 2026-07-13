import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { SavedTariff, TariffApiService } from '../../../core/services/tariff-api.service';

@Component({
  selector: 'app-tariff-list',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './tariff-list.component.html',
  styleUrl: './tariff-list.component.scss',
})
export class TariffListComponent {
  readonly form: FormGroup;
  tariffs: SavedTariff[] | null = null;
  loading = false;
  loadError: string | null = null;

  constructor(
    private readonly fb: FormBuilder,
    private readonly tariffApi: TariffApiService,
  ) {
    this.form = this.fb.group({ tenantId: ['', Validators.required] });
  }

  load(): void {
    if (this.form.invalid) {
      return;
    }
    this.loading = true;
    this.loadError = null;
    const tenantId = this.form.value.tenantId;
    this.tariffApi.list(tenantId).subscribe({
      next: (tariffs) => {
        this.tariffs = tariffs;
        this.loading = false;
      },
      error: () => {
        this.loadError = 'Failed to load tariffs for this tenant.';
        this.loading = false;
      },
    });
  }
}
