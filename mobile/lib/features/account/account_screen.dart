import 'package:flutter/material.dart';

import '../../core/auth/auth_session.dart';
import '../../core/models/reservation.dart';

typedef ReservationsFetcher = Future<List<Reservation>> Function();
typedef ReservationCanceler = Future<void> Function(String reservationId);

class AccountScreen extends StatefulWidget {
  final AuthSession authSession;
  final ReservationsFetcher? fetchReservations;
  final ReservationCanceler? cancelReservation;

  const AccountScreen({
    super.key,
    required this.authSession,
    this.fetchReservations,
    this.cancelReservation,
  });

  @override
  State<AccountScreen> createState() => _AccountScreenState();
}

class _AccountScreenState extends State<AccountScreen> {
  List<Reservation> _reservations = [];
  bool _loadingReservations = true;
  String? _reservationsError;

  @override
  void initState() {
    super.initState();
    if (widget.fetchReservations != null) {
      _loadReservations();
    } else {
      _loadingReservations = false;
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
        ],
      ),
    );
  }
}
