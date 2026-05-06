import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        color: const Color(0xFF1A1A1A),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text(
              'Oracle Gallery',
              style: TextStyle(
                color: const Color(0xFFC9A84C),
                fontSize: 48,
                fontFamily: 'Cinzel',
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'Atmospheric intro text...',
              style: TextStyle(
                color: const Color(0xFFCCC5B8),
                fontSize: 16,
                fontFamily: 'EB Garamond',
              ),
            ),
            const SizedBox(height: 40),
            ElevatedButton(
              onPressed: () {
                // Navigate to cloth page
                Navigator.pushNamed(context, '/cloth');
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFC9A84C),
                foregroundColor: const Color(0xFF1A1A1A),
                padding: EdgeInsets.symmetric(horizontal: 40, vertical: 15),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8.0),
                ),
              ),
              child: const Text(
                'Explore The Cloth',
                style: TextStyle(
                  color: const Color(0xFF1A1A1A),
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: () {
                // Navigate to marks page
                Navigator.pushNamed(context, '/marks');
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFCCC5B8),
                foregroundColor: const Color(0xFF1A1A1A),
                padding: EdgeInsets.symmetric(horizontal: 40, vertical: 15),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8.0),
                ),
              ),
              child: const Text(
                'View The Marks',
                style: TextStyle(
                  color: const Color(0xFF1A1A1A),
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: () {
                // Navigate to about page
                Navigator.pushNamed(context, '/about');
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFCCC5B8),
                foregroundColor: const Color(0xFF1A1A1A),
                padding: EdgeInsets.symmetric(horizontal: 40, vertical: 15),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8.0),
                ),
              ),
              child: const Text(
                'About',
                style: TextStyle(
                  color: const Color(0xFF1A1A1A),
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
