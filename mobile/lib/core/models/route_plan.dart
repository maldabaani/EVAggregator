class SuggestedCharger {
  final String id;
  final String? name;
  final double lat;
  final double lng;

  const SuggestedCharger({required this.id, required this.name, required this.lat, required this.lng});

  factory SuggestedCharger.fromJson(Map<String, dynamic> json) => SuggestedCharger(
        id: json['id'] as String,
        name: json['name'] as String?,
        lat: (json['lat'] as num).toDouble(),
        lng: (json['lng'] as num).toDouble(),
      );
}

class RoutePlanResult {
  final double distanceKm;
  final double durationMinutes;
  final bool chargingStopNeeded;
  final SuggestedCharger? suggestedCharger;

  const RoutePlanResult({
    required this.distanceKm,
    required this.durationMinutes,
    required this.chargingStopNeeded,
    required this.suggestedCharger,
  });

  factory RoutePlanResult.fromJson(Map<String, dynamic> json) => RoutePlanResult(
        distanceKm: (json['distance_km'] as num).toDouble(),
        durationMinutes: (json['duration_minutes'] as num).toDouble(),
        chargingStopNeeded: json['charging_stop_needed'] as bool,
        suggestedCharger: json['suggested_charger'] == null
            ? null
            : SuggestedCharger.fromJson(json['suggested_charger'] as Map<String, dynamic>),
      );
}
