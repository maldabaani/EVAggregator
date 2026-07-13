class Reservation {
  final String id;
  final String chargerId;
  final int connectorId;
  final DateTime expiresAt;

  const Reservation({
    required this.id,
    required this.chargerId,
    required this.connectorId,
    required this.expiresAt,
  });

  factory Reservation.fromJson(Map<String, dynamic> json) => Reservation(
        id: json['id'] as String,
        chargerId: json['charger_id'] as String,
        connectorId: json['connector_id'] as int,
        expiresAt: DateTime.parse(json['expires_at'] as String),
      );
}
