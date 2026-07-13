import 'package:flutter/material.dart';

import '../../core/models/route_plan.dart';
import '../../core/models/vehicle.dart';

typedef VehiclesFetcher = Future<List<Vehicle>> Function();
typedef RoutePlanner = Future<RoutePlanResult> Function(
  String vehicleId,
  double originLat,
  double originLng,
  double destinationLat,
  double destinationLng,
);

/// Origin/destination are entered as coordinates, not place names — no
/// geocoding backend exists yet (see `DriverApi.searchStations`'s own
/// docs on the same gap), so this is honest about only accepting what
/// the backend can actually resolve.
class RoutePlannerScreen extends StatefulWidget {
  final VehiclesFetcher fetchVehicles;
  final RoutePlanner planRoute;

  const RoutePlannerScreen({super.key, required this.fetchVehicles, required this.planRoute});

  @override
  State<RoutePlannerScreen> createState() => _RoutePlannerScreenState();
}

class _RoutePlannerScreenState extends State<RoutePlannerScreen> {
  final _originLatController = TextEditingController();
  final _originLngController = TextEditingController();
  final _destinationLatController = TextEditingController();
  final _destinationLngController = TextEditingController();

  List<Vehicle> _vehicles = [];
  String? _selectedVehicleId;
  bool _loadingVehicles = true;
  String? _loadError;

  bool _planning = false;
  String? _planError;
  RoutePlanResult? _result;

  @override
  void initState() {
    super.initState();
    _loadVehicles();
  }

  @override
  void dispose() {
    _originLatController.dispose();
    _originLngController.dispose();
    _destinationLatController.dispose();
    _destinationLngController.dispose();
    super.dispose();
  }

  Future<void> _loadVehicles() async {
    setState(() {
      _loadingVehicles = true;
      _loadError = null;
    });
    try {
      final vehicles = await widget.fetchVehicles();
      if (!mounted) return;
      setState(() {
        _vehicles = vehicles;
        _selectedVehicleId = vehicles.isEmpty ? null : vehicles.first.id;
        _loadingVehicles = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loadingVehicles = false;
        _loadError = 'Could not load your vehicles.';
      });
    }
  }

  Future<void> _submit() async {
    final originLat = double.tryParse(_originLatController.text);
    final originLng = double.tryParse(_originLngController.text);
    final destinationLat = double.tryParse(_destinationLatController.text);
    final destinationLng = double.tryParse(_destinationLngController.text);
    if (_selectedVehicleId == null ||
        originLat == null ||
        originLng == null ||
        destinationLat == null ||
        destinationLng == null) {
      setState(() => _planError = 'Select a vehicle and enter valid coordinates for both points.');
      return;
    }
    setState(() {
      _planning = true;
      _planError = null;
      _result = null;
    });
    try {
      final result = await widget.planRoute(_selectedVehicleId!, originLat, originLng, destinationLat, destinationLng);
      if (!mounted) return;
      setState(() => _result = result);
    } catch (_) {
      if (!mounted) return;
      setState(() => _planError = 'Could not plan this route. Please try again.');
    } finally {
      if (mounted) setState(() => _planning = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Route Planner')),
      body: _loadingVehicles
          ? const Center(child: CircularProgressIndicator(key: Key('route-planner-loading')))
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                if (_loadError != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(_loadError!, key: const Key('route-planner-load-error'),
                        style: const TextStyle(color: Colors.red)),
                  ),
                if (_vehicles.isEmpty)
                  const Text('Add a vehicle first to plan a route.', key: Key('route-planner-no-vehicles'))
                else ...[
                  DropdownButtonFormField<String>(
                    key: const Key('route-planner-vehicle-dropdown'),
                    initialValue: _selectedVehicleId,
                    decoration: const InputDecoration(labelText: 'Vehicle'),
                    items: _vehicles
                        .map((v) => DropdownMenuItem(value: v.id, child: Text('${v.make} ${v.model}')))
                        .toList(),
                    onChanged: (value) => setState(() => _selectedVehicleId = value),
                  ),
                  const SizedBox(height: 16),
                  Text('Origin', style: Theme.of(context).textTheme.titleSmall),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          key: const Key('route-planner-origin-lat-field'),
                          controller: _originLatController,
                          decoration: const InputDecoration(labelText: 'Latitude'),
                          keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextField(
                          key: const Key('route-planner-origin-lng-field'),
                          controller: _originLngController,
                          decoration: const InputDecoration(labelText: 'Longitude'),
                          keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Text('Destination', style: Theme.of(context).textTheme.titleSmall),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          key: const Key('route-planner-destination-lat-field'),
                          controller: _destinationLatController,
                          decoration: const InputDecoration(labelText: 'Latitude'),
                          keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextField(
                          key: const Key('route-planner-destination-lng-field'),
                          controller: _destinationLngController,
                          decoration: const InputDecoration(labelText: 'Longitude'),
                          keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                        ),
                      ),
                    ],
                  ),
                  if (_planError != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Text(_planError!, key: const Key('route-planner-error'),
                          style: const TextStyle(color: Colors.red)),
                    ),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    key: const Key('route-planner-submit-button'),
                    onPressed: _planning ? null : _submit,
                    child: _planning
                        ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Text('Plan route'),
                  ),
                  if (_result != null) ...[
                    const SizedBox(height: 24),
                    Card(
                      key: const Key('route-planner-result'),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('${_result!.distanceKm.toStringAsFixed(1)} km · '
                                '${_result!.durationMinutes.round()} min'),
                            const SizedBox(height: 8),
                            if (_result!.chargingStopNeeded)
                              Text(
                                _result!.suggestedCharger == null
                                    ? 'A charging stop is recommended, but no station could be suggested.'
                                    : 'Charging stop recommended at '
                                        '${_result!.suggestedCharger!.name ?? _result!.suggestedCharger!.id}.',
                                key: const Key('route-planner-charging-stop'),
                              )
                            else
                              const Text(
                                'No charging stop needed for this trip.',
                                key: Key('route-planner-no-stop-needed'),
                              ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ],
              ],
            ),
    );
  }
}
