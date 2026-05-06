import 'package:flutter/material.dart';

class CreamCard extends StatelessWidget {
  final Widget child;

  const CreamCard({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFFF7F4EF),
        borderRadius: BorderRadius.circular(8.0),
      ),
      child: child,
    );
  }
}

class GoldAccentText extends StatelessWidget {
  final String text;
  final TextStyle? style;

  const GoldAccentText(this.text, {super.key, this.style});

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: GoogleFonts.era(
        color: const Color(0xFFC9A84C),
        fontSize: 16,
        fontWeight: FontWeight.w700,
        letterSpacing: 0.5,
      ).copyWith(style),
    );
  }
}
