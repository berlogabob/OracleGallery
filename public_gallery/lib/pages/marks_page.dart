import 'package:flutter/material.dart';

class MarksPage extends StatelessWidget {
  const MarksPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: const Color(0xFF1A1A1A),
        foregroundColor: const Color(0xFFC9A84C),
        title: const Text('The Marks'),
        centerTitle: true,
      ),
      body: GridView.builder(
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 3,
          childAspectRatio: 1.0,
        ),
        itemCount: 8,
        itemBuilder: (context, index) {
          return Card(
            color: const Color(0xFF1A1A1A),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // Placeholder for SVG
                Container(
                  width: 60,
                  height: 60,
                  color: const Color(0xFFCCC5B8),
                ),
                const SizedBox(height: 8),
                Text(
                  'Mark \${index + 1}',
                  style: GoogleFonts.cinzel(
                    color: const Color(0xFFC9A84C),
                    fontSize: 16,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Description of mark \${index + 1} goes here.',
                  style: GoogleFonts.ebGaramond(
                    color: const Color(0xFFCCC5B8),
                    fontSize: 12,
                  ),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
