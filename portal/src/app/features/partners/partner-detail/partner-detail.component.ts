import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';

import { ReconciliationEntry } from '../../../core/models/partner.model';
import { PartnerApiService } from '../../../core/services/partner-api.service';
import { SavedTariff, TariffApiService } from '../../../core/services/tariff-api.service';

type TabId = 'credentials' | 'price-lists' | 'reconciliation';

@Component({
  selector: 'app-partner-detail',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './partner-detail.component.html',
  styleUrl: './partner-detail.component.scss',
})
export class PartnerDetailComponent implements OnInit {
  partnerId = '';
  activeTab: TabId = 'credentials';
  rotatedToken: string | null = null;
  rotateTokenError: string | null = null;
  reconciliationEntries: ReconciliationEntry[] = [];
  reconciliationStatusFilter = '';
  reconciliationError: string | null = null;

  tariffs: SavedTariff[] = [];
  tariffsError: string | null = null;

  priceListForm = {
    connectorType: 'CCS2',
    tariffId: '',
    effectiveFrom: '',
  };
  priceListSaved = false;
  priceListError: string | null = null;

  constructor(
    private readonly route: ActivatedRoute,
    private readonly partnerApi: PartnerApiService,
    private readonly tariffApi: TariffApiService,
  ) {}

  ngOnInit(): void {
    this.partnerId = this.route.snapshot.paramMap.get('id') ?? '';
    this.loadReconciliation();
    this.loadTariffs();
  }

  setTab(tab: TabId): void {
    this.activeTab = tab;
  }

  loadTariffs(): void {
    this.tariffsError = null;
    this.partnerApi.listPartners().subscribe({
      next: (partners) => {
        const partner = partners.find((p) => p.id === this.partnerId);
        if (!partner) {
          this.tariffsError = 'Could not determine this partner\'s tenant.';
          return;
        }
        this.tariffApi.list(partner.tenant_id).subscribe({
          next: (tariffs) => (this.tariffs = tariffs),
          error: () => (this.tariffsError = 'Could not load tariffs.'),
        });
      },
      error: () => (this.tariffsError = 'Could not load tariffs.'),
    });
  }

  rotateToken(): void {
    this.rotateTokenError = null;
    this.partnerApi.rotateToken(this.partnerId).subscribe({
      next: (response) => (this.rotatedToken = response.token_a),
      error: () => (this.rotateTokenError = `Could not rotate the token for partner "${this.partnerId}".`),
    });
  }

  attachPriceList(): void {
    this.priceListError = null;
    this.priceListSaved = false;
    this.partnerApi
      .attachPriceList(this.partnerId, {
        connectorType: this.priceListForm.connectorType,
        tariffId: this.priceListForm.tariffId,
        effectiveFrom: this.priceListForm.effectiveFrom,
      })
      .subscribe({
        next: () => {
          this.priceListForm = { connectorType: 'CCS2', tariffId: '', effectiveFrom: '' };
          this.priceListSaved = true;
        },
        error: () => (this.priceListError = 'Could not attach the price list. Please try again.'),
      });
  }

  loadReconciliation(): void {
    this.reconciliationError = null;
    this.partnerApi.getReconciliation(this.reconciliationStatusFilter || undefined).subscribe({
      next: (entries) => (this.reconciliationEntries = entries),
      error: () => (this.reconciliationError = 'Could not load reconciliation results.'),
    });
  }

  get exportUrl(): string {
    return this.partnerApi.reconciliationExportUrl(this.reconciliationStatusFilter || undefined);
  }
}
