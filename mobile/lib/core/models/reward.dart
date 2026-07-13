class RewardCatalogItem {
  final String id;
  final String name;
  final int pointsCost;

  const RewardCatalogItem({
    required this.id,
    required this.name,
    required this.pointsCost,
  });

  factory RewardCatalogItem.fromJson(Map<String, dynamic> json) => RewardCatalogItem(
        id: json['id'] as String,
        name: json['name'] as String,
        pointsCost: json['points_cost'] as int,
      );
}

class RewardsSummary {
  final int balance;
  final List<RewardCatalogItem> catalog;

  const RewardsSummary({required this.balance, required this.catalog});

  factory RewardsSummary.fromJson(Map<String, dynamic> json) => RewardsSummary(
        balance: json['balance'] as int,
        catalog: (json['catalog'] as List<dynamic>)
            .map((item) => RewardCatalogItem.fromJson(item as Map<String, dynamic>))
            .toList(),
      );
}
