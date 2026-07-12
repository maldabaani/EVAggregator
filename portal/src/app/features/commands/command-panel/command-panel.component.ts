import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';

import {
  COMMAND_PAYLOAD_HINTS,
  COMMAND_TYPES,
  CommandLogRecord,
  CommandResult,
  CommandType,
} from '../../../core/models/command.model';
import { CommandApiService } from '../../../core/services/command-api.service';

@Component({
  selector: 'app-command-panel',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './command-panel.component.html',
  styleUrl: './command-panel.component.scss',
})
export class CommandPanelComponent {
  readonly form: FormGroup;
  readonly commandTypes = COMMAND_TYPES;

  sending = false;
  sendError: string | null = null;
  lastResult: CommandResult | null = null;

  log: CommandLogRecord[] = [];
  logLoading = false;
  logError: string | null = null;
  logLoaded = false;

  constructor(
    private readonly fb: FormBuilder,
    private readonly commandApi: CommandApiService,
  ) {
    this.form = this.fb.group({
      chargerId: ['', Validators.required],
      tenantId: ['', Validators.required],
      commandType: [COMMAND_TYPES[0] as CommandType, Validators.required],
      payload: [COMMAND_PAYLOAD_HINTS[COMMAND_TYPES[0]], Validators.required],
    });
  }

  get payloadHint(): string {
    return COMMAND_PAYLOAD_HINTS[this.form.value.commandType as CommandType];
  }

  onCommandTypeChange(): void {
    this.form.patchValue({ payload: this.payloadHint });
  }

  send(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(this.form.value.payload || '{}');
    } catch {
      this.sendError = 'Payload must be valid JSON.';
      return;
    }

    const { chargerId, tenantId, commandType } = this.form.value;
    this.sending = true;
    this.sendError = null;
    this.lastResult = null;

    this.commandApi.sendCommand(chargerId, tenantId, commandType, payload).subscribe({
      next: (result) => {
        this.lastResult = result;
        this.sending = false;
        this.loadLog();
      },
      error: (err) => {
        this.sendError =
          err?.status === 409
            ? `${chargerId} is offline — the command was rejected before it ever reached the charger.`
            : 'Could not send the command. Please try again.';
        this.sending = false;
      },
    });
  }

  loadLog(): void {
    const chargerId = this.form.value.chargerId;
    if (!chargerId) {
      return;
    }
    this.logLoading = true;
    this.logError = null;
    this.commandApi.listRecent(chargerId).subscribe({
      next: (records) => {
        this.log = records;
        this.logLoading = false;
        this.logLoaded = true;
      },
      error: () => {
        this.logError = 'Could not load the command log. Please try again.';
        this.logLoading = false;
      },
    });
  }

  resultJson(result: Record<string, unknown> | null): string {
    return result ? JSON.stringify(result, null, 2) : '—';
  }
}
