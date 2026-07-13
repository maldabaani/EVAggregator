const String walletBalanceType = 'wallet_balance';
const String directCardType = 'direct_card';

class PaymentMethod {
  final String type;
  final String? pspToken;
  final bool isDefault;

  const PaymentMethod({required this.type, this.pspToken, required this.isDefault});

  factory PaymentMethod.fromJson(Map<String, dynamic> json) => PaymentMethod(
        type: json['type'] as String,
        pspToken: json['psp_token'] as String?,
        isDefault: json['is_default'] as bool,
      );
}
