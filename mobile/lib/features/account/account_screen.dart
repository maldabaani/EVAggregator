import 'package:flutter/material.dart';

import '../../core/auth/auth_session.dart';

class AccountScreen extends StatelessWidget {
  final AuthSession authSession;

  const AccountScreen({super.key, required this.authSession});

  @override
  Widget build(BuildContext context) {
    final driver = authSession.driver;
    return Scaffold(
      appBar: AppBar(title: const Text('Account')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
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
              onPressed: authSession.logout,
              child: const Text('Log out'),
            ),
          ],
        ),
      ),
    );
  }
}
