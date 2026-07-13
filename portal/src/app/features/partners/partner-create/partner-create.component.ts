import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { CreatedPartner } from '../../../core/models/partner.model';
import { PartnerApiService } from '../../../core/services/partner-api.service';

@Component({
  selector: 'app-partner-create',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './partner-create.component.html',
  styleUrl: './partner-create.component.scss',
})
export class PartnerCreateComponent {
  readonly form: FormGroup;
  saving = false;
  saveError: string | null = null;
  created: CreatedPartner | null = null;

  constructor(
    private readonly fb: FormBuilder,
    private readonly partnerApi: PartnerApiService,
    private readonly router: Router,
  ) {
    this.form = this.fb.group({
      tenantId: ['', Validators.required],
      partyId: ['', [Validators.required, Validators.maxLength(3)]],
      countryCode: ['', [Validators.required, Validators.maxLength(2)]],
    });
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const { tenantId, partyId, countryCode } = this.form.value;
    this.saving = true;
    this.saveError = null;

    this.partnerApi.createPartner(tenantId, partyId.toUpperCase(), countryCode.toUpperCase()).subscribe({
      next: (partner) => {
        this.created = partner;
        this.saving = false;
      },
      error: () => {
        this.saveError = 'Could not create the partner. Please check the details and try again.';
        this.saving = false;
      },
    });
  }

  goToPartner(): void {
    if (this.created) {
      this.router.navigate(['/partners', this.created.id]);
    }
  }
}
