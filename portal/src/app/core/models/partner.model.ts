export interface Partner {
  id: string;
  party_id: string;
  country_code: string;
  negotiated_version: string | null;
  status: 'pending' | 'connected' | 'suspended';
  last_handshake_at: string | null;
}

export interface ReconciliationEntry {
  local_cdr_id: string | null;
  partner_cdr_uid: string;
  status: 'matched' | 'mismatched' | 'pending';
  delta_fraction: number | null;
}

export interface PriceListAttachment {
  connectorType: string;
  tariffId: string;
  effectiveFrom: string;
}
