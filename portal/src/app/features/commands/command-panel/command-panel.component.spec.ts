import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CommandLogRecordApiResponse, CommandResultApiResponse } from '../../../core/models/command.model';
import { CommandPanelComponent } from './command-panel.component';

const CHARGER_ID = 'CP-001';
const TENANT_ID = 'tenant-123';

function sampleResult(overrides: Partial<CommandResultApiResponse> = {}): CommandResultApiResponse {
  return {
    command_id: 'cmd-1',
    status: 'accepted',
    result: { status: 'Accepted' },
    ...overrides,
  };
}

function sampleLogRecord(overrides: Partial<CommandLogRecordApiResponse> = {}): CommandLogRecordApiResponse {
  return {
    command_id: 'cmd-1',
    charger_id: CHARGER_ID,
    tenant_id: TENANT_ID,
    type: 'Reset',
    status: 'accepted',
    requested_at: '2026-07-12T10:00:00Z',
    responded_at: '2026-07-12T10:00:01Z',
    result: { status: 'Accepted' },
    ...overrides,
  };
}

describe('CommandPanelComponent', () => {
  let fixture: ComponentFixture<CommandPanelComponent>;
  let component: CommandPanelComponent;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CommandPanelComponent, HttpClientTestingModule],
    }).compileComponents();

    fixture = TestBed.createComponent(CommandPanelComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  afterEach(() => httpMock.verify());

  function compiled(): HTMLElement {
    return fixture.nativeElement;
  }

  function fillChargerAndTenant(): void {
    component.form.patchValue({ chargerId: CHARGER_ID, tenantId: TENANT_ID });
  }

  it('does not fire a request when charger ID is empty', () => {
    compiled().querySelector<HTMLButtonElement>('[data-testid="send-command-button"]')!.click();
    fixture.detectChanges();

    expect(component.form.invalid).toBeTrue();
    httpMock.expectNone(() => true);
  });

  it('sends the command with the selected type and JSON payload, and shows the result', () => {
    fillChargerAndTenant();
    component.form.patchValue({ commandType: 'Reset', payload: '{ "type": "Soft" }' });
    component.send();

    const req = httpMock.expectOne((r) => r.url === `/admin/chargers/${CHARGER_ID}/commands`);
    expect(req.request.body).toEqual({
      tenant_id: TENANT_ID,
      command_type: 'Reset',
      payload: { type: 'Soft' },
    });
    req.flush(sampleResult());
    fixture.detectChanges();

    // Sending a command triggers a log refresh.
    httpMock.expectOne((r) => r.url === `/admin/chargers/${CHARGER_ID}/commands`).flush([]);
    fixture.detectChanges();

    expect(compiled().querySelector('[data-testid="last-result-status"]')?.textContent).toContain('accepted');
    expect(compiled().querySelector('[data-testid="last-result-id"]')?.textContent).toContain('cmd-1');
  });

  it('shows a JSON error and never fires a request when the payload is invalid', () => {
    fillChargerAndTenant();
    component.form.patchValue({ payload: 'not json' });
    component.send();
    fixture.detectChanges();

    expect(compiled().querySelector('[data-testid="send-error"]')?.textContent).toContain('valid JSON');
    httpMock.expectNone(() => true);
  });

  it('shows a friendly offline message on a 409 response', () => {
    fillChargerAndTenant();
    component.send();

    httpMock
      .expectOne((r) => r.url === `/admin/chargers/${CHARGER_ID}/commands`)
      .flush('offline', { status: 409, statusText: 'Conflict' });
    fixture.detectChanges();

    expect(compiled().querySelector('[data-testid="send-error"]')?.textContent).toContain('offline');
  });

  it('updating the command type replaces the payload with that command\'s hint', () => {
    fillChargerAndTenant();
    component.form.patchValue({ commandType: 'ClearCache' });
    component.onCommandTypeChange();

    expect(component.form.value.payload).toBe('{}');
  });

  it('loads and displays the recent command log', () => {
    fillChargerAndTenant();
    component.loadLog();

    httpMock.expectOne((r) => r.url === `/admin/chargers/${CHARGER_ID}/commands`).flush([sampleLogRecord()]);
    fixture.detectChanges();

    const rows = compiled().querySelectorAll('[data-testid="log-row"]');
    expect(rows.length).toBe(1);
    expect(rows[0].textContent).toContain('Reset');
    expect(rows[0].textContent).toContain('accepted');
  });

  it('shows the empty state when the log has no records', () => {
    fillChargerAndTenant();
    component.loadLog();

    httpMock.expectOne((r) => r.url === `/admin/chargers/${CHARGER_ID}/commands`).flush([]);
    fixture.detectChanges();

    expect(compiled().querySelector('[data-testid="log-empty-state"]')).toBeTruthy();
  });

  it('shows an error state when the log request fails', () => {
    fillChargerAndTenant();
    component.loadLog();

    httpMock
      .expectOne((r) => r.url === `/admin/chargers/${CHARGER_ID}/commands`)
      .flush('boom', { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();

    expect(compiled().querySelector('[data-testid="log-error-state"]')).toBeTruthy();
  });
});
