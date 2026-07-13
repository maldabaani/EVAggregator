import 'package:flutter/material.dart';

import '../../core/auth/auth_session.dart';

class SignupScreen extends StatefulWidget {
  final AuthSession authSession;
  final VoidCallback onSwitchToLogin;

  const SignupScreen({super.key, required this.authSession, required this.onSwitchToLogin});

  @override
  State<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends State<SignupScreen> {
  final _fullNameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _fullNameController.dispose();
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
      await widget.authSession.signup(
        email: _emailController.text,
        fullName: _fullNameController.text,
        password: _passwordController.text,
      );
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Could not create your account. Please try again.');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Sign up')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              key: const Key('signup-full-name-field'),
              controller: _fullNameController,
              decoration: const InputDecoration(labelText: 'Full name'),
            ),
            const SizedBox(height: 12),
            TextField(
              key: const Key('signup-email-field'),
              controller: _emailController,
              decoration: const InputDecoration(labelText: 'Email'),
              keyboardType: TextInputType.emailAddress,
            ),
            const SizedBox(height: 12),
            TextField(
              key: const Key('signup-password-field'),
              controller: _passwordController,
              decoration: const InputDecoration(labelText: 'Password'),
              obscureText: true,
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_error!, key: const Key('signup-error'), style: const TextStyle(color: Colors.red)),
              ),
            const SizedBox(height: 24),
            ElevatedButton(
              key: const Key('signup-submit-button'),
              onPressed: _submitting ? null : _submit,
              child: _submitting
                  ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Sign up'),
            ),
            TextButton(
              key: const Key('switch-to-login-button'),
              onPressed: widget.onSwitchToLogin,
              child: const Text('Already have an account? Log in'),
            ),
          ],
        ),
      ),
    );
  }
}
