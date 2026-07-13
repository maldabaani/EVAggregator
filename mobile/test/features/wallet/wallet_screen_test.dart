import 'package:evagg_driver/core/models/payment_method.dart';
import 'package:evagg_driver/features/wallet/wallet_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _wrap(Widget child) => MaterialApp(home: child);

void main() {
  testWidgets('shows the balance and defaults the radio to the fetched payment method', (tester) async {
    await tester.pumpWidget(_wrap(WalletScreen(
      fetchBalance: () async => 12345,
      topUp: (amount, token, currency) async {},
      fetchPaymentMethod: () async => const PaymentMethod(type: directCardType, pspToken: 'tok-1', isDefault: true),
      setPaymentMethod: (type, token) async => PaymentMethod(type: type, pspToken: token, isDefault: true),
    )));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('wallet-balance-value')), findsOneWidget);
    expect(find.textContaining('123.45'), findsOneWidget);
    final cardRadio = tester.widget<RadioListTile<String>>(
      find.byKey(const Key('payment-method-direct-card-radio')),
    );
    expect(cardRadio.groupValue, directCardType);
  });

  testWidgets('shows a load error banner when loading the wallet fails', (tester) async {
    await tester.pumpWidget(_wrap(WalletScreen(
      fetchBalance: () async => throw Exception('boom'),
      topUp: (amount, token, currency) async {},
      fetchPaymentMethod: () async => null,
      setPaymentMethod: (type, token) async => const PaymentMethod(type: walletBalanceType, isDefault: true),
    )));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('wallet-load-error')), findsOneWidget);
  });

  testWidgets('topping up calls topUp with the amount converted to minor units', (tester) async {
    int? capturedAmount;
    String? capturedToken;

    await tester.pumpWidget(_wrap(WalletScreen(
      fetchBalance: () async => 0,
      topUp: (amount, token, currency) async {
        capturedAmount = amount;
        capturedToken = token;
      },
      fetchPaymentMethod: () async => null,
      setPaymentMethod: (type, token) async => const PaymentMethod(type: walletBalanceType, isDefault: true),
    )));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('show-topup-form-button')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('topup-amount-field')), '50');
    await tester.enterText(find.byKey(const Key('topup-psp-token-field')), 'tok-1');
    await tester.tap(find.byKey(const Key('submit-topup-button')));
    await tester.pumpAndSettle();

    expect(capturedAmount, 5000);
    expect(capturedToken, 'tok-1');
    expect(find.byKey(const Key('topup-form')), findsNothing);
  });

  testWidgets('an invalid top-up form shows an error and never calls topUp', (tester) async {
    var topUpCalled = false;

    await tester.pumpWidget(_wrap(WalletScreen(
      fetchBalance: () async => 0,
      topUp: (amount, token, currency) async => topUpCalled = true,
      fetchPaymentMethod: () async => null,
      setPaymentMethod: (type, token) async => const PaymentMethod(type: walletBalanceType, isDefault: true),
    )));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('show-topup-form-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('submit-topup-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('topup-error')), findsOneWidget);
    expect(topUpCalled, isFalse);
  });

  testWidgets('a failed top-up shows an inline error', (tester) async {
    await tester.pumpWidget(_wrap(WalletScreen(
      fetchBalance: () async => 0,
      topUp: (amount, token, currency) async => throw Exception('declined'),
      fetchPaymentMethod: () async => null,
      setPaymentMethod: (type, token) async => const PaymentMethod(type: walletBalanceType, isDefault: true),
    )));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('show-topup-form-button')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('topup-amount-field')), '50');
    await tester.enterText(find.byKey(const Key('topup-psp-token-field')), 'tok-1');
    await tester.tap(find.byKey(const Key('submit-topup-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('topup-error')), findsOneWidget);
  });

  testWidgets('selecting Card and saving requires a psp token', (tester) async {
    var setCalled = false;

    await tester.pumpWidget(_wrap(WalletScreen(
      fetchBalance: () async => 0,
      topUp: (amount, token, currency) async {},
      fetchPaymentMethod: () async => null,
      setPaymentMethod: (type, token) async {
        setCalled = true;
        return PaymentMethod(type: type, pspToken: token, isDefault: true);
      },
    )));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('payment-method-direct-card-radio')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('save-payment-method-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('payment-method-error')), findsOneWidget);
    expect(setCalled, isFalse);
  });

  testWidgets('saving Wallet balance as the payment method needs no token and shows confirmation', (tester) async {
    String? capturedType;

    await tester.pumpWidget(_wrap(WalletScreen(
      fetchBalance: () async => 0,
      topUp: (amount, token, currency) async {},
      fetchPaymentMethod: () async => null,
      setPaymentMethod: (type, token) async {
        capturedType = type;
        return PaymentMethod(type: type, pspToken: token, isDefault: true);
      },
    )));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('save-payment-method-button')));
    await tester.pumpAndSettle();

    expect(capturedType, walletBalanceType);
    expect(find.byKey(const Key('payment-method-saved')), findsOneWidget);
  });

  testWidgets('saving Card with a token succeeds', (tester) async {
    String? capturedToken;

    await tester.pumpWidget(_wrap(WalletScreen(
      fetchBalance: () async => 0,
      topUp: (amount, token, currency) async {},
      fetchPaymentMethod: () async => null,
      setPaymentMethod: (type, token) async {
        capturedToken = token;
        return PaymentMethod(type: type, pspToken: token, isDefault: true);
      },
    )));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('payment-method-direct-card-radio')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('payment-method-psp-token-field')), 'tok-1');
    await tester.tap(find.byKey(const Key('save-payment-method-button')));
    await tester.pumpAndSettle();

    expect(capturedToken, 'tok-1');
    expect(find.byKey(const Key('payment-method-saved')), findsOneWidget);
  });
}
