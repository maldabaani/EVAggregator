import 'package:flutter/material.dart';

import '../../core/models/payment_method.dart';
import '../session/session_tracking.dart' show formatCost;

typedef BalanceFetcher = Future<int> Function();
typedef TopUpHandler = Future<void> Function(int amountMinorUnits, String pspToken, String currency);
typedef PaymentMethodFetcher = Future<PaymentMethod?> Function();
typedef PaymentMethodSetter = Future<PaymentMethod> Function(String type, String? pspToken);

/// The wallet doesn't carry its own currency (the backend's
/// `GET /wallet/balance` response has none) — every other cost display in
/// this app (insights_screen.dart) already assumes AED for the same
/// reason, so this matches that existing convention rather than
/// inventing a different placeholder.
const String _walletCurrency = 'AED';

class WalletScreen extends StatefulWidget {
  final BalanceFetcher fetchBalance;
  final TopUpHandler topUp;
  final PaymentMethodFetcher fetchPaymentMethod;
  final PaymentMethodSetter setPaymentMethod;

  const WalletScreen({
    super.key,
    required this.fetchBalance,
    required this.topUp,
    required this.fetchPaymentMethod,
    required this.setPaymentMethod,
  });

  @override
  State<WalletScreen> createState() => _WalletScreenState();
}

class _WalletScreenState extends State<WalletScreen> {
  bool _loading = true;
  String? _loadError;
  int? _balanceMinorUnits;

  bool _showTopUpForm = false;
  final _amountController = TextEditingController();
  final _pspTokenController = TextEditingController();
  bool _submittingTopUp = false;
  String? _topUpError;

  String _selectedMethodType = walletBalanceType;
  final _methodPspTokenController = TextEditingController();
  bool _savingMethod = false;
  String? _methodError;
  bool _methodSaved = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _amountController.dispose();
    _pspTokenController.dispose();
    _methodPspTokenController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final results = await Future.wait([widget.fetchBalance(), widget.fetchPaymentMethod()]);
      if (!mounted) return;
      final method = results[1] as PaymentMethod?;
      setState(() {
        _balanceMinorUnits = results[0] as int;
        _selectedMethodType = method?.type ?? walletBalanceType;
        _methodPspTokenController.text = method?.pspToken ?? '';
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadError = 'Could not load your wallet. Please try again.';
      });
    }
  }

  Future<void> _submitTopUp() async {
    final amount = double.tryParse(_amountController.text);
    if (amount == null || amount <= 0 || _pspTokenController.text.trim().isEmpty) {
      setState(() => _topUpError = 'Enter an amount and a payment token.');
      return;
    }
    setState(() {
      _submittingTopUp = true;
      _topUpError = null;
    });
    try {
      await widget.topUp((amount * 100).round(), _pspTokenController.text.trim(), _walletCurrency);
      _amountController.clear();
      _pspTokenController.clear();
      if (!mounted) return;
      setState(() => _showTopUpForm = false);
      await _load();
    } catch (_) {
      if (!mounted) return;
      setState(() => _topUpError = 'Could not top up your wallet. Please try again.');
    } finally {
      if (mounted) setState(() => _submittingTopUp = false);
    }
  }

  Future<void> _submitPaymentMethod() async {
    if (_selectedMethodType == directCardType && _methodPspTokenController.text.trim().isEmpty) {
      setState(() => _methodError = 'Enter a card payment token.');
      return;
    }
    setState(() {
      _savingMethod = true;
      _methodError = null;
      _methodSaved = false;
    });
    try {
      await widget.setPaymentMethod(
        _selectedMethodType,
        _selectedMethodType == directCardType ? _methodPspTokenController.text.trim() : null,
      );
      if (!mounted) return;
      setState(() => _methodSaved = true);
    } catch (_) {
      if (!mounted) return;
      setState(() => _methodError = 'Could not save your payment method. Please try again.');
    } finally {
      if (mounted) setState(() => _savingMethod = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Wallet')),
      body: _loading
          ? const Center(child: CircularProgressIndicator(key: Key('wallet-loading')))
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
                        key: const Key('wallet-load-error'),
                        style: const TextStyle(color: Colors.red),
                      ),
                    ),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Balance', style: Theme.of(context).textTheme.labelMedium),
                          Text(
                            formatCost(_balanceMinorUnits ?? 0, _walletCurrency),
                            key: const Key('wallet-balance-value'),
                            style: Theme.of(context).textTheme.headlineMedium,
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  if (!_showTopUpForm)
                    OutlinedButton(
                      key: const Key('show-topup-form-button'),
                      onPressed: () => setState(() => _showTopUpForm = true),
                      child: const Text('Top up'),
                    )
                  else
                    Card(
                      key: const Key('topup-form'),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            TextField(
                              key: const Key('topup-amount-field'),
                              controller: _amountController,
                              decoration: const InputDecoration(labelText: 'Amount (AED)'),
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                            ),
                            TextField(
                              key: const Key('topup-psp-token-field'),
                              controller: _pspTokenController,
                              decoration: const InputDecoration(labelText: 'Card payment token'),
                            ),
                            if (_topUpError != null)
                              Padding(
                                padding: const EdgeInsets.only(top: 8),
                                child: Text(
                                  _topUpError!,
                                  key: const Key('topup-error'),
                                  style: const TextStyle(color: Colors.red),
                                ),
                              ),
                            const SizedBox(height: 8),
                            ElevatedButton(
                              key: const Key('submit-topup-button'),
                              onPressed: _submittingTopUp ? null : _submitTopUp,
                              child: _submittingTopUp
                                  ? const SizedBox(
                                      height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                                  : const Text('Confirm top up'),
                            ),
                          ],
                        ),
                      ),
                    ),
                  const SizedBox(height: 24),
                  Text('Payment method', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  RadioListTile<String>(
                    key: const Key('payment-method-wallet-balance-radio'),
                    title: const Text('Wallet balance'),
                    value: walletBalanceType,
                    groupValue: _selectedMethodType,
                    onChanged: (value) => setState(() => _selectedMethodType = value ?? walletBalanceType),
                  ),
                  RadioListTile<String>(
                    key: const Key('payment-method-direct-card-radio'),
                    title: const Text('Card'),
                    value: directCardType,
                    groupValue: _selectedMethodType,
                    onChanged: (value) => setState(() => _selectedMethodType = value ?? walletBalanceType),
                  ),
                  if (_selectedMethodType == directCardType)
                    TextField(
                      key: const Key('payment-method-psp-token-field'),
                      controller: _methodPspTokenController,
                      decoration: const InputDecoration(labelText: 'Card payment token'),
                    ),
                  if (_methodError != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        _methodError!,
                        key: const Key('payment-method-error'),
                        style: const TextStyle(color: Colors.red),
                      ),
                    ),
                  if (_methodSaved)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        'Payment method saved.',
                        key: const Key('payment-method-saved'),
                        style: TextStyle(color: Colors.green.shade700),
                      ),
                    ),
                  const SizedBox(height: 12),
                  ElevatedButton(
                    key: const Key('save-payment-method-button'),
                    onPressed: _savingMethod ? null : _submitPaymentMethod,
                    child: _savingMethod
                        ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Text('Save payment method'),
                  ),
                ],
              ),
            ),
    );
  }
}
