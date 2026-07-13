export interface Partner {
  id: string;
  tenant_id: string;
  party_id: string;
  country_code: string;
  negotiated_version: string | null;
  status: 'pending' | 'connected' | 'suspended';
  last_handshake_at: string | null;
}

/** Only returned once, by createPartner — no later read ever exposes token_a again. */
export interface CreatedPartner extends Partner {
  token_a: string;
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
