import 'package:flutter/material.dart';

import '../../core/models/reservation.dart';
import '../../core/models/reward.dart';
import '../../core/models/vehicle.dart';
import '../account/account_screen.dart' show ReservationsFetcher, RewardsFetcher;
import '../analytics/insights_screen.dart' show UsageFetcher;
import '../analytics/usage_insights.dart';
import '../session/session_tracking.dart' show formatCost;
import '../vehicles/vehicle_list_screen.dart' show VehiclesFetcher;
import '../wallet/wallet_screen.dart' show BalanceFetcher;

/// The driver's dashboard tab — a single at-a-glance summary of the app's
/// real features (vehicles, wallet, weekly charging activity, reservations,
/// rewards), each loaded and failed independently so one slow/broken
/// endpoint never blanks the rest of the screen. Every action here routes
/// to a tab that already exists; there is no vehicle remote-control,
/// smart-charging, or notification widget because this app has no backend
/// behind those.
class HomeScreen extends StatefulWidget {
  final VehiclesFetcher fetchVehicles;
  final BalanceFetcher fetchWalletBalance;
  final UsageFetcher fetchUsageInsights;
  final ReservationsFetcher? fetchReservations;
  final RewardsFetcher? fetchRewards;
  final VoidCallback onOpenMap;
  final VoidCallback? onOpenVehicles;
  final VoidCallback? onOpenWallet;

  const HomeScreen({
    super.key,
    required this.fetchVehicles,
    required this.fetchWalletBalance,
    required this.fetchUsageInsights,
    this.fetchReservations,
    this.fetchRewards,
    required this.onOpenMap,
    this.onOpenVehicles,
    this.onOpenWallet,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List<Vehicle> _vehicles = [];
  bool _loadingVehicles = true;
  bool _vehiclesFailed = false;

  int? _balanceMinorUnits;
  bool _loadingBalance = true;
  bool _balanceFailed = false;

  UsageSummary _usage = UsageSummary.zero;
  bool _loadingUsage = true;
  bool _usageFailed = false;

  List<Reservation> _reservations = [];
  bool _loadingReservations = true;

  RewardsSummary? _rewards;
  bool _loadingRewards = true;

  @override
  void initState() {
    super.initState();
    if (widget.fetchReservations == null) _loadingReservations = false;
    if (widget.fetchRewards == null) _loadingRewards = false;
    _loadAll();
  }

  Future<void> _loadAll() async {
    await Future.wait([
      _loadVehicles(),
      _loadBalance(),
      _loadUsage(),
      if (widget.fetchReservations != null) _loadReservations(),
      if (widget.fetchRewards != null) _loadRewards(),
    ]);
  }

  Future<void> _loadVehicles() async {
    try {
      final vehicles = await widget.fetchVehicles();
      if (!mounted) return;
      setState(() {
        _vehicles = vehicles;
        _vehiclesFailed = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _vehiclesFailed = true);
    } finally {
      if (mounted) setState(() => _loadingVehicles = false);
    }
  }

  Future<void> _loadBalance() async {
    try {
      final balance = await widget.fetchWalletBalance();
      if (!mounted) return;
      setState(() {
        _balanceMinorUnits = balance;
        _balanceFailed = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _balanceFailed = true);
    } finally {
      if (mounted) setState(() => _loadingBalance = false);
    }
  }

  Future<void> _loadUsage() async {
    try {
      final to = DateTime.now();
      final from = to.subtract(const Duration(days: 7));
      final points = await widget.fetchUsageInsights(from, to);
      if (!mounted) return;
      setState(() {
        _usage = summarize(points);
        _usageFailed = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _usageFailed = true);
    } finally {
      if (mounted) setState(() => _loadingUsage = false);
    }
  }

  Future<void> _loadReservations() async {
    try {
      final reservations = await widget.fetchReservations!();
      if (!mounted) return;
      setState(() => _reservations = reservations);
    } catch (_) {
      // A failed reservations fetch just means the upcoming-reservation
      // card doesn't show — the rest of the dashboard is unaffected.
    } finally {
      if (mounted) setState(() => _loadingReservations = false);
    }
  }

  Future<void> _loadRewards() async {
    try {
      final rewards = await widget.fetchRewards!();
      if (!mounted) return;
      setState(() => _rewards = rewards);
    } catch (_) {
      // Same as reservations — silently omit the teaser on failure.
    } finally {
      if (mounted) setState(() => _loadingRewards = false);
    }
  }

  Reservation? get _nextReservation {
    if (_reservations.isEmpty) return null;
    final upcoming = _reservations.where((r) => r.expiresAt.isAfter(DateTime.now())).toList()
      ..sort((a, b) => a.expiresAt.compareTo(b.expiresAt));
    return upcoming.isEmpty ? null : upcoming.first;
  }

  @override
  Widget build(BuildContext context) {
    final loading = _loadingVehicles || _loadingBalance || _loadingUsage || _loadingReservations || _loadingRewards;
    return Scaffold(
      appBar: AppBar(title: const Text('Home')),
      body: RefreshIndicator(
        onRefresh: _loadAll,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (loading && _vehicles.isEmpty && !_vehiclesFailed)
              const Center(child: CircularProgressIndicator(key: Key('home-loading')))
            else ...[
              _buildVehicleCard(context),
              const SizedBox(height: 16),
              _buildWalletCard(context),
              const SizedBox(height: 16),
              _buildUsageCard(context),
              if (_nextReservation != null) ...[
                const SizedBox(height: 16),
                _buildReservationCard(context, _nextReservation!),
              ],
              if (_rewards != null) ...[
                const SizedBox(height: 16),
                _buildRewardsTeaser(context, _rewards!),
              ],
              const SizedBox(height: 16),
              FilledButton.icon(
                key: const Key('home-open-map-button'),
                onPressed: widget.onOpenMap,
                icon: const Icon(Icons.ev_station),
                label: const Text('Find charging near you'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildVehicleCard(BuildContext context) {
    if (_vehiclesFailed) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Text('Could not load your vehicles.', key: Key('home-vehicles-error')),
        ),
      );
    }
    if (_vehicles.isEmpty) {
      return Card(
        key: const Key('home-no-vehicle'),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('No vehicle yet', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              const Text('Add a vehicle to start charging and track usage.'),
              if (widget.onOpenVehicles != null) ...[
                const SizedBox(height: 8),
                TextButton(
                  key: const Key('home-open-vehicles-button'),
                  onPressed: widget.onOpenVehicles,
                  child: const Text('Add a vehicle'),
                ),
              ],
            ],
          ),
        ),
      );
    }
    final vehicle = _vehicles.first;
    return Card(
      key: const Key('home-vehicle-card'),
      child: ListTile(
        leading: const Icon(Icons.directions_car, size: 32),
        title: Text('${vehicle.make} ${vehicle.model}'),
        subtitle: Text(
          '${vehicle.batteryCapacityKwh.toStringAsFixed(0)} kWh · '
          '${vehicle.plugAndChargeEnabled ? 'Plug & Charge on' : 'Plug & Charge off'}',
        ),
        trailing: widget.onOpenVehicles == null
            ? null
            : IconButton(
                key: const Key('home-open-vehicles-button'),
                icon: const Icon(Icons.chevron_right),
                onPressed: widget.onOpenVehicles,
              ),
      ),
    );
  }

  Widget _buildWalletCard(BuildContext context) {
    return Card(
      child: ListTile(
        key: const Key('home-wallet-balance'),
        leading: const Icon(Icons.account_balance_wallet, size: 32),
        title: const Text('Wallet balance'),
        subtitle: _balanceFailed
            ? const Text('Could not load your balance.')
            : Text(formatCost(_balanceMinorUnits ?? 0, 'AED')),
        trailing: widget.onOpenWallet == null
            ? null
            : IconButton(
                key: const Key('home-open-wallet-button'),
                icon: const Icon(Icons.chevron_right),
                onPressed: widget.onOpenWallet,
              ),
      ),
    );
  }

  Widget _buildUsageCard(BuildContext context) {
    return Card(
      key: const Key('home-usage-summary'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('This week', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            if (_usageFailed)
              const Text('Could not load your charging activity.')
            else
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  _usageStat('Sessions', '${_usage.totalSessions}'),
                  _usageStat('Energy', '${_usage.totalKwh.toStringAsFixed(1)} kWh'),
                  _usageStat('Spend', formatCost(_usage.totalCostMinorUnits, 'AED')),
                ],
              ),
          ],
        ),
      ),
    );
  }

  Widget _usageStat(String label, String value) {
    return Column(
      children: [
        Text(value, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
        const SizedBox(height: 4),
        Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
      ],
    );
  }

  Widget _buildReservationCard(BuildContext context, Reservation reservation) {
    return Card(
      key: Key('home-reservation-card-${reservation.id}'),
      child: ListTile(
        leading: const Icon(Icons.event_available, size: 32),
        title: Text('Reservation at ${reservation.chargerId}'),
        subtitle: Text('Connector ${reservation.connectorId} · until ${reservation.expiresAt.toLocal()}'),
      ),
    );
  }

  Widget _buildRewardsTeaser(BuildContext context, RewardsSummary rewards) {
    return Card(
      key: const Key('home-rewards-teaser'),
      child: ListTile(
        leading: const Icon(Icons.card_giftcard, size: 32),
        title: const Text('Rewards'),
        subtitle: Text('${rewards.balance} points available'),
      ),
    );
  }
}
