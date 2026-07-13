import 'package:flutter/material.dart';

import '../../core/models/vehicle.dart';

typedef VehiclesFetcher = Future<List<Vehicle>> Function();
typedef VehicleCreator = Future<Vehicle> Function(
  String make,
  String model,
  String connectorType,
  double batteryCapacityKwh,
);
typedef PlugAndChargeToggler = Future<void> Function(String vehicleId, bool enabled);
typedef VehicleDeleter = Future<void> Function(String vehicleId);

/// "My Cars" — foundation for the route planner (needs battery capacity)
/// and per-vehicle Plug & Charge opt-in.
class VehicleListScreen extends StatefulWidget {
  final VehiclesFetcher fetcher;
  final VehicleCreator creator;
  final PlugAndChargeToggler toggler;
  final VehicleDeleter deleter;

  const VehicleListScreen({
    super.key,
    required this.fetcher,
    required this.creator,
    required this.toggler,
    required this.deleter,
  });

  @override
  State<VehicleListScreen> createState() => _VehicleListScreenState();
}

class _VehicleListScreenState extends State<VehicleListScreen> {
  List<Vehicle> _vehicles = [];
  bool _loading = true;
  String? _loadError;
  bool _showAddForm = false;
  bool _saving = false;
  String? _saveError;

  final _makeController = TextEditingController();
  final _modelController = TextEditingController();
  final _connectorController = TextEditingController(text: 'CCS2');
  final _batteryController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _makeController.dispose();
    _modelController.dispose();
    _connectorController.dispose();
    _batteryController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final vehicles = await widget.fetcher();
      if (!mounted) return;
      setState(() {
        _vehicles = vehicles;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadError = 'Could not load your vehicles.';
      });
    }
  }

  Future<void> _submitAdd() async {
    final battery = double.tryParse(_batteryController.text);
    if (_makeController.text.trim().isEmpty || _modelController.text.trim().isEmpty || battery == null) {
      setState(() => _saveError = 'Fill in make, model, and a numeric battery capacity.');
      return;
    }
    setState(() {
      _saving = true;
      _saveError = null;
    });
    try {
      await widget.creator(
        _makeController.text.trim(),
        _modelController.text.trim(),
        _connectorController.text.trim(),
        battery,
      );
      _makeController.clear();
      _modelController.clear();
      _batteryController.clear();
      if (!mounted) return;
      setState(() => _showAddForm = false);
      await _load();
    } catch (_) {
      if (!mounted) return;
      setState(() => _saveError = 'Could not add this vehicle. Please try again.');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _toggle(Vehicle vehicle, bool enabled) async {
    try {
      await widget.toggler(vehicle.id, enabled);
      await _load();
    } catch (_) {
      if (!mounted) return;
      setState(() => _loadError = 'Could not update Plug & Charge for this vehicle.');
    }
  }

  Future<void> _delete(Vehicle vehicle) async {
    try {
      await widget.deleter(vehicle.id);
      await _load();
    } catch (_) {
      if (!mounted) return;
      setState(() => _loadError = 'Could not remove this vehicle.');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('My Cars')),
      floatingActionButton: FloatingActionButton(
        key: const Key('add-vehicle-fab'),
        onPressed: () => setState(() => _showAddForm = !_showAddForm),
        child: Icon(_showAddForm ? Icons.close : Icons.add),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(key: Key('vehicles-loading')))
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  if (_loadError != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(
                        _loadError!,
                        key: const Key('vehicles-load-error'),
                        style: const TextStyle(color: Colors.red),
                      ),
                    ),
                  if (_showAddForm) _buildAddForm(),
                  if (_vehicles.isEmpty && !_showAddForm)
                    const Padding(
                      padding: EdgeInsets.only(top: 32),
                      child: Center(
                        key: Key('vehicles-empty-state'),
                        child: Text('No vehicles yet. Tap + to add one.'),
                      ),
                    ),
                  ..._vehicles.map(_buildVehicleTile),
                ],
              ),
            ),
    );
  }

  Widget _buildAddForm() {
    return Card(
      key: const Key('add-vehicle-form'),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              key: const Key('vehicle-make-field'),
              controller: _makeController,
              decoration: const InputDecoration(labelText: 'Make'),
            ),
            TextField(
              key: const Key('vehicle-model-field'),
              controller: _modelController,
              decoration: const InputDecoration(labelText: 'Model'),
            ),
            TextField(
              key: const Key('vehicle-connector-field'),
              controller: _connectorController,
              decoration: const InputDecoration(labelText: 'Connector type'),
            ),
            TextField(
              key: const Key('vehicle-battery-field'),
              controller: _batteryController,
              decoration: const InputDecoration(labelText: 'Battery capacity (kWh)'),
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
            ),
            if (_saveError != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  _saveError!,
                  key: const Key('vehicle-save-error'),
                  style: const TextStyle(color: Colors.red),
                ),
              ),
            const SizedBox(height: 8),
            ElevatedButton(
              key: const Key('save-vehicle-button'),
              onPressed: _saving ? null : _submitAdd,
              child: _saving
                  ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Save vehicle'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildVehicleTile(Vehicle vehicle) {
    return Card(
      key: Key('vehicle-tile-${vehicle.id}'),
      child: ListTile(
        title: Text('${vehicle.make} ${vehicle.model}'),
        subtitle: Text('${vehicle.connectorType} · ${vehicle.batteryCapacityKwh.toStringAsFixed(0)} kWh'),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Switch(
              key: Key('plug-and-charge-switch-${vehicle.id}'),
              value: vehicle.plugAndChargeEnabled,
              onChanged: (value) => _toggle(vehicle, value),
            ),
            IconButton(
              key: Key('delete-vehicle-button-${vehicle.id}'),
              icon: const Icon(Icons.delete_outline),
              onPressed: () => _delete(vehicle),
            ),
          ],
        ),
      ),
    );
  }
}
