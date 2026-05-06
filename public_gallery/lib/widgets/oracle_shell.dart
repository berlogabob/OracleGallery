import 'package:flutter/material.dart';

class OracleShell extends StatelessWidget {
  final Widget child;

  const OracleShell({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        color: const Color(0xFF1A1A1A),
        child: child,
      ),
    );
  }
}
