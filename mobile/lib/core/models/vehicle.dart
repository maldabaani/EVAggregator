class Vehicle {
  final String id;
  final String make;
  final String model;
  final String connectorType;
  final double batteryCapacityKwh;
  final bool plugAndChargeEnabled;

  const Vehicle({
    required this.id,
    required this.make,
    required this.model,
    required this.connectorType,
    required this.batteryCapacityKwh,
    required this.plugAndChargeEnabled,
  });

  factory Vehicle.fromJson(Map<String, dynamic> json) => Vehicle(
        id: json['id'] as String,
        make: json['make'] as String,
        model: json['model'] as String,
        connectorType: json['connector_type'] as String,
        batteryCapacityKwh: (json['battery_capacity_kwh'] as num).toDouble(),
        plugAndChargeEnabled: json['plug_and_charge_enabled'] as bool,
      );
}
