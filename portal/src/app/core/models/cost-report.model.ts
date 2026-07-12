export const GROUP_BY_DRIVER = 'driver';
export const GROUP_BY_SITE = 'site';
export type CostReportGroupBy = typeof GROUP_BY_DRIVER | typeof GROUP_BY_SITE;

export interface CostReportRow {
  key: string;
  sessionCount: number;
  kwhTotal: number;
  costTotalMinorUnits: number;
}

export interface CostReport {
  groupBy: CostReportGroupBy;
  rows: CostReportRow[];
  totalSessionCount: number;
  totalKwh: number;
  totalCostMinorUnits: number;
  incompleteDates: string[];
}

/** Wire shape returned by GET /admin/teams/{team_id}/cost-report (snake_case). */
export interface CostReportApiResponse {
  group_by: CostReportGroupBy;
  rows: { key: string; session_count: number; kwh_total: number; cost_total_minor_units: number }[];
  total_session_count: number;
  total_kwh: number;
  total_cost_minor_units: number;
  incomplete_dates: string[];
}

export function fromApiResponse(response: CostReportApiResponse): CostReport {
  return {
    groupBy: response.group_by,
    rows: response.rows.map((row) => ({
      key: row.key,
      sessionCount: row.session_count,
      kwhTotal: row.kwh_total,
      costTotalMinorUnits: row.cost_total_minor_units,
    })),
    totalSessionCount: response.total_session_count,
    totalKwh: response.total_kwh,
    totalCostMinorUnits: response.total_cost_minor_units,
    incompleteDates: response.incomplete_dates,
  };
}
