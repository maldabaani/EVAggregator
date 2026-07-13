import 'package:flutter/material.dart';

import '../../core/auth/auth_session.dart';

class LoginScreen extends StatefulWidget {
  final AuthSession authSession;
  final VoidCallback onSwitchToSignup;

  const LoginScreen({super.key, required this.authSession, required this.onSwitchToSignup});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.authSession.login(email: _emailController.text, password: _passwordController.text);
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Could not log in. Check your email and password.');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Log in')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              key: const Key('login-email-field'),
              controller: _emailController,
              decoration: const InputDecoration(labelText: 'Email'),
              keyboardType: TextInputType.emailAddress,
            ),
            const SizedBox(height: 12),
            TextField(
              key: const Key('login-password-field'),
              controller: _passwordController,
              decoration: const InputDecoration(labelText: 'Password'),
              obscureText: true,
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_error!, key: const Key('login-error'), style: const TextStyle(color: Colors.red)),
              ),
            const SizedBox(height: 24),
            ElevatedButton(
              key: const Key('login-submit-button'),
              onPressed: _submitting ? null : _submit,
              child: _submitting
                  ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Log in'),
            ),
            TextButton(
              key: const Key('switch-to-signup-button'),
              onPressed: widget.onSwitchToSignup,
              child: const Text("Don't have an account? Sign up"),
            ),
          ],
        ),
      ),
    );
  }
}
