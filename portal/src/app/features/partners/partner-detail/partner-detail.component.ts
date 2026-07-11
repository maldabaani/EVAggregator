import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';

import { ReconciliationEntry } from '../../../core/models/partner.model';
import { PartnerApiService } from '../../../core/services/partner-api.service';

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
  reconciliationEntries: ReconciliationEntry[] = [];
  reconciliationStatusFilter = '';

  priceListForm = {
    connectorType: 'CCS2',
    tariffId: '',
    effectiveFrom: '',
  };

  constructor(
    private readonly route: ActivatedRoute,
    private readonly partnerApi: PartnerApiService,
  ) {}

  ngOnInit(): void {
    this.partnerId = this.route.snapshot.paramMap.get('id') ?? '';
    this.loadReconciliation();
  }

  setTab(tab: TabId): void {
    this.activeTab = tab;
  }

  rotateToken(): void {
    this.partnerApi.rotateToken(this.partnerId).subscribe((response) => {
      this.rotatedToken = response.token_a;
    });
  }

  attachPriceList(): void {
    this.partnerApi
      .attachPriceList(this.partnerId, {
        connectorType: this.priceListForm.connectorType,
        tariffId: this.priceListForm.tariffId,
        effectiveFrom: this.priceListForm.effectiveFrom,
      })
      .subscribe(() => {
        this.priceListForm = { connectorType: 'CCS2', tariffId: '', effectiveFrom: '' };
      });
  }

  loadReconciliation(): void {
    this.partnerApi.getReconciliation(this.reconciliationStatusFilter || undefined).subscribe((entries) => {
      this.reconciliationEntries = entries;
    });
  }

  get exportUrl(): string {
    return this.partnerApi.reconciliationExportUrl(this.reconciliationStatusFilter || undefined);
  }
}
