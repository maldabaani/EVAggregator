import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Observable } from 'rxjs';

import { Partner } from '../../core/models/partner.model';
import { PartnerApiService } from '../../core/services/partner-api.service';

interface DashboardPanel {
  title: string;
  description: string;
  link: string;
  linkLabel: string;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  partners$!: Observable<Partner[]>;

  readonly panels: DashboardPanel[] = [
    {
      title: 'Roaming Partners',
      description: 'Onboard OCPI partners, rotate credentials, and review CDR reconciliation.',
      link: '/partners',
      linkLabel: 'View partners',
    },
    {
      title: 'Tariffs',
      description: 'Build multi-component pricing (energy, time, flat, idle) for your chargers.',
      link: '/tariffs',
      linkLabel: 'View tariffs',
    },
    {
      title: 'Cost Reports',
      description: 'Session cost rollups grouped by driver or by site over a date range.',
      link: '/cost-dashboard',
      linkLabel: 'Open cost reports',
    },
    {
      title: 'Remote Commands',
      description: 'Send OCPP remote-start/stop/reset commands and review the command log.',
      link: '/commands',
      linkLabel: 'Open commands',
    },
  ];

  constructor(private readonly partnerApi: PartnerApiService) {}

  ngOnInit(): void {
    this.partners$ = this.partnerApi.listPartners();
  }

  connectedCount(partners: Partner[]): number {
    return partners.filter((p) => p.status === 'connected').length;
  }
}
