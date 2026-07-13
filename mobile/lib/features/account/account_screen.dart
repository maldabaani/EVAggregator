import 'package:flutter/material.dart';

import '../../core/auth/auth_session.dart';
import '../../core/models/reservation.dart';
import '../../core/models/reward.dart';
import '../analytics/insights_screen.dart';

typedef ReservationsFetcher = Future<List<Reservation>> Function();
typedef ReservationCanceler = Future<void> Function(String reservationId);
typedef RewardsFetcher = Future<RewardsSummary> Function();
typedef RewardRedeemer = Future<int> Function(String rewardId);

class AccountScreen extends StatefulWidget {
  final AuthSession authSession;
  final ReservationsFetcher? fetchReservations;
  final ReservationCanceler? cancelReservation;
  final RewardsFetcher? fetchRewards;
  final RewardRedeemer? redeemReward;
  final UsageFetcher? fetchUsageInsights;

  const AccountScreen({
    super.key,
    required this.authSession,
    this.fetchReservations,
    this.cancelReservation,
    this.fetchRewards,
    this.redeemReward,
    this.fetchUsageInsights,
  });

  @override
  State<AccountScreen> createState() => _AccountScreenState();
}

class _AccountScreenState extends State<AccountScreen> {
  List<Reservation> _reservations = [];
  bool _loadingReservations = true;
  String? _reservationsError;

  RewardsSummary? _rewards;
  bool _loadingRewards = true;
  String? _rewardsError;
  String? _redeemingRewardId;

  @override
  void initState() {
    super.initState();
    if (widget.fetchReservations != null) {
      _loadReservations();
    } else {
      _loadingReservations = false;
    }
    if (widget.fetchRewards != null) {
      _loadRewards();
    } else {
      _loadingRewards = false;
    }
  }

  Future<void> _loadReservations() async {
    setState(() {
      _loadingReservations = true;
      _reservationsError = null;
    });
    try {
      final reservations = await widget.fetchReservations!();
      if (!mounted) return;
      setState(() {
        _reservations = reservations;
        _loadingReservations = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loadingReservations = false;
        _reservationsError = 'Could not load your reservations.';
      });
    }
  }

  Future<void> _cancel(Reservation reservation) async {
    try {
      await widget.cancelReservation!(reservation.id);
      await _loadReservations();
    } catch (_) {
      if (!mounted) return;
      setState(() => _reservationsError = 'Could not cancel this reservation.');
    }
  }

  Future<void> _loadRewards() async {
    setState(() {
      _loadingRewards = true;
      _rewardsError = null;
    });
    try {
      final rewards = await widget.fetchRewards!();
      if (!mounted) return;
      setState(() {
        _rewards = rewards;
        _loadingRewards = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loadingRewards = false;
        _rewardsError = 'Could not load your rewards.';
      });
    }
  }

  Future<void> _redeem(RewardCatalogItem item) async {
    setState(() {
      _redeemingRewardId = item.id;
      _rewardsError = null;
    });
    try {
      await widget.redeemReward!(item.id);
      await _loadRewards();
    } catch (_) {
      if (!mounted) return;
      setState(() => _rewardsError = 'Could not redeem "${item.name}".');
    } finally {
      if (mounted) setState(() => _redeemingRewardId = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final driver = widget.authSession.driver;
    return Scaffold(
      appBar: AppBar(title: const Text('Account')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            driver?.fullName ?? '',
            key: const Key('account-full-name'),
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 4),
          Text(driver?.email ?? '', key: const Key('account-email')),
          const SizedBox(height: 24),
          ElevatedButton(
            key: const Key('logout-button'),
            onPressed: widget.authSession.logout,
            child: const Text('Log out'),
          ),
          if (widget.fetchUsageInsights != null) ...[
            const SizedBox(height: 12),
            OutlinedButton(
              key: const Key('open-insights-button'),
              onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => InsightsScreen(fetcher: widget.fetchUsageInsights!),
              )),
              child: const Text('Charging insights'),
            ),
          ],
          if (widget.fetchReservations != null) ...[
            const SizedBox(height: 32),
            Text('My reservations', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (_loadingReservations)
              const Center(child: CircularProgressIndicator(key: Key('reservations-loading')))
            else if (_reservationsError != null)
              Text(
                _reservationsError!,
                key: const Key('reservations-error'),
                style: const TextStyle(color: Colors.red),
              )
            else if (_reservations.isEmpty)
              const Text('No active reservations.', key: Key('reservations-empty'))
            else
              ..._reservations.map(
                (reservation) => Card(
                  key: Key('reservation-tile-${reservation.id}'),
                  child: ListTile(
                    title: Text('${reservation.chargerId} · connector ${reservation.connectorId}'),
                    subtitle: Text('Until ${reservation.expiresAt.toLocal()}'),
                    trailing: widget.cancelReservation == null
                        ? null
                        : IconButton(
                            key: Key('cancel-reservation-button-${reservation.id}'),
                            icon: const Icon(Icons.cancel_outlined),
                            onPressed: () => _cancel(reservation),
                          ),
                  ),
                ),
              ),
          ],
          if (widget.fetchRewards != null) ...[
            const SizedBox(height: 32),
            Text('Rewards', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (_loadingRewards)
              const Center(child: CircularProgressIndicator(key: Key('rewards-loading')))
            else if (_rewardsError != null)
              Text(
                _rewardsError!,
                key: const Key('rewards-error'),
                style: const TextStyle(color: Colors.red),
              )
            else if (_rewards != null) ...[
              Text('${_rewards!.balance} points', key: const Key('rewards-balance')),
              const SizedBox(height: 8),
              ..._rewards!.catalog.map(
                (item) => Card(
                  key: Key('reward-tile-${item.id}'),
                  child: ListTile(
                    title: Text(item.name),
                    subtitle: Text('${item.pointsCost} points'),
                    trailing: widget.redeemReward == null
                        ? null
                        : ElevatedButton(
                            key: Key('redeem-reward-button-${item.id}'),
                            onPressed: (_redeemingRewardId != null || _rewards!.balance < item.pointsCost)
                                ? null
                                : () => _redeem(item),
                            child: Text(_redeemingRewardId == item.id ? 'Redeeming…' : 'Redeem'),
                          ),
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
