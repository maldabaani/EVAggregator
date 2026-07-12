export const COMMAND_TYPES = [
  'RemoteStartTransaction',
  'RemoteStopTransaction',
  'Reset',
  'UnlockConnector',
  'ChangeConfiguration',
  'GetConfiguration',
  'ClearCache',
  'TriggerMessage',
  'GetDiagnostics',
] as const;

export type CommandType = (typeof COMMAND_TYPES)[number];

/** Placeholder payload shown per command type — a nudge, not validation;
 * the backend is the source of truth for what each command actually needs. */
export const COMMAND_PAYLOAD_HINTS: Record<CommandType, string> = {
  RemoteStartTransaction: '{ "idTag": "TAG-123", "connectorId": 1 }',
  RemoteStopTransaction: '{ "transactionId": 42 }',
  Reset: '{ "type": "Soft" }',
  UnlockConnector: '{ "connectorId": 1 }',
  ChangeConfiguration: '{ "key": "HeartbeatInterval", "value": "300" }',
  GetConfiguration: '{ "key": ["HeartbeatInterval"] }',
  ClearCache: '{}',
  TriggerMessage: '{ "requestedMessage": "StatusNotification", "connectorId": 1 }',
  GetDiagnostics: '{ "location": "https://example.com/upload" }',
};

export type CommandStatus = 'pending' | 'accepted' | 'rejected' | 'timed_out';

export interface CommandResult {
  commandId: string;
  status: CommandStatus;
  result: Record<string, unknown> | null;
}

export interface CommandResultApiResponse {
  command_id: string;
  status: CommandStatus;
  result: Record<string, unknown> | null;
}

export interface CommandLogRecord {
  commandId: string;
  chargerId: string;
  tenantId: string;
  type: string;
  status: CommandStatus;
  requestedAt: string;
  respondedAt: string | null;
  result: Record<string, unknown> | null;
}

export interface CommandLogRecordApiResponse {
  command_id: string;
  charger_id: string;
  tenant_id: string;
  type: string;
  status: CommandStatus;
  requested_at: string;
  responded_at: string | null;
  result: Record<string, unknown> | null;
}

export function fromResultApiResponse(response: CommandResultApiResponse): CommandResult {
  return { commandId: response.command_id, status: response.status, result: response.result };
}

export function fromRecordApiResponse(response: CommandLogRecordApiResponse): CommandLogRecord {
  return {
    commandId: response.command_id,
    chargerId: response.charger_id,
    tenantId: response.tenant_id,
    type: response.type,
    status: response.status,
    requestedAt: response.requested_at,
    respondedAt: response.responded_at,
    result: response.result,
  };
}
