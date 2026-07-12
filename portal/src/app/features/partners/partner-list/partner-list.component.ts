import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Observable } from 'rxjs';

import { Partner } from '../../../core/models/partner.model';
import { PartnerApiService } from '../../../core/services/partner-api.service';

@Component({
  selector: 'app-partner-list',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './partner-list.component.html',
  styleUrl: './partner-list.component.scss',
})
export class PartnerListComponent implements OnInit {
  partners$!: Observable<Partner[]>;

  constructor(private readonly partnerApi: PartnerApiService) {}

  ngOnInit(): void {
    this.partners$ = this.partnerApi.listPartners();
  }
}
