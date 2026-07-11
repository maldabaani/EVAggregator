import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';

import { CostReport, CostReportGroupBy, GROUP_BY_DRIVER, GROUP_BY_SITE } from '../../core/models/cost-report.model';
import { CostReportApiService } from '../../core/services/cost-report-api.service';

export interface CostDashboardRowView {
  key: string;
  sessionCount: number;
  kwhTotal: number;
  costLabel: string;
  barPercent: number;
}

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function formatCost(minorUnits: number): string {
  return (minorUnits / 100).toFixed(2);
}

const DEFAULT_WINDOW_DAYS = 30;

@Component({
  selector: 'app-cost-dashboard',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './cost-dashboard.component.html',
  styleUrl: './cost-dashboard.component.scss',
})
export class CostDashboardComponent {
  readonly form: FormGroup;
  readonly groupByDriver = GROUP_BY_DRIVER;
  readonly groupBySite = GROUP_BY_SITE;

  report: CostReport | null = null;
  loading = false;
  errorMessage: string | null = null;

  constructor(
    private readonly fb: FormBuilder,
    private readonly costReportApi: CostReportApiService,
  ) {
    const today = new Date();
    const windowStart = new Date(today);
    windowStart.setDate(windowStart.getDate() - (DEFAULT_WINDOW_DAYS - 1));

    this.form = this.fb.group({
      teamId: ['', Validators.required],
      dateFrom: [isoDate(windowStart), Validators.required],
      dateTo: [isoDate(today), Validators.required],
      groupBy: [GROUP_BY_DRIVER as CostReportGroupBy, Validators.required],
    });
  }

  get groupBy(): CostReportGroupBy {
    return this.form.value.groupBy;
  }

  setGroupBy(groupBy: CostReportGroupBy): void {
    this.form.patchValue({ groupBy });
    if (this.report) {
      this.load();
    }
  }

  load(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const { teamId, dateFrom, dateTo, groupBy } = this.form.value;
    this.loading = true;
    this.errorMessage = null;
    this.costReportApi.getReport(teamId, dateFrom, dateTo, groupBy).subscribe({
      next: (report) => {
        this.report = report;
        this.loading = false;
      },
      error: () => {
        this.errorMessage = 'Could not load the cost report. Please try again.';
        this.loading = false;
      },
    });
  }

  get totalCostLabel(): string {
    return this.report ? formatCost(this.report.totalCostMinorUnits) : '0.00';
  }

  get averageCostPerSessionLabel(): string {
    if (!this.report || this.report.totalSessionCount === 0) {
      return '—';
    }
    return formatCost(this.report.totalCostMinorUnits / this.report.totalSessionCount);
  }

  get rowViews(): CostDashboardRowView[] {
    if (!this.report || this.report.rows.length === 0) {
      return [];
    }
    const maxCost = Math.max(...this.report.rows.map((r) => r.costTotalMinorUnits), 1);
    return [...this.report.rows]
      .sort((a, b) => b.costTotalMinorUnits - a.costTotalMinorUnits)
      .map((row) => ({
        key: row.key,
        sessionCount: row.sessionCount,
        kwhTotal: row.kwhTotal,
        costLabel: formatCost(row.costTotalMinorUnits),
        barPercent: Math.round((row.costTotalMinorUnits / maxCost) * 100),
      }));
  }

  get csvUrl(): string {
    const { teamId, dateFrom, dateTo, groupBy } = this.form.value;
    if (!teamId) {
      return '';
    }
    return this.costReportApi.csvDownloadUrl(teamId, dateFrom, dateTo, groupBy);
  }
}
