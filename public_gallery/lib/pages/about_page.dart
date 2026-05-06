import 'package:flutter/material.dart';

class AboutPage extends StatelessWidget {
  const AboutPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: const Color(0xFF1A1A1A),
        foregroundColor: const Color(0xFFC9A84C),
        title: const Text('About'),
        centerTitle: true,
      ),
      body: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Project Context',
                style: TextStyle(
                  color: const Color(0xFFC9A84C),
                  fontSize: 24,
                  fontFamily: 'Cinzel',
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'This is a placeholder for project context text. It should describe the background and purpose of the Oracle Gallery project.',
                style: TextStyle(
                  color: const Color(0xFFCCC5B8),
                  fontSize: 16,
                  fontFamily: 'EB Garamond',
                ),
              ),
              const SizedBox(height: 24),
              const Text(
                'How It Works',
                style: TextStyle(
                  color: const Color(0xFFC9A84C),
                  fontSize: 24,
                  fontFamily: 'Cinzel',
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Description of how the Oracle Gallery works, including the AI systems and process for creating marks and sessions.',
                style: TextStyle(
                  color: const Color(0xFFCCC5B8),
                  fontSize: 16,
                  fontFamily: 'EB Garamond',
                ),
              ),
              const SizedBox(height: 24),
              const Text(
                'AI Systems',
                style: TextStyle(
                  color: const Color(0xFFC9A84C),
                  fontSize: 24,
                  fontFamily: 'Cinzel',
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Information about the AI systems used in the Oracle Gallery, including details about the models and their capabilities.',
                style: TextStyle(
                  color: const Color(0xFFCCC5B8),
                  fontSize: 16,
                  fontFamily: 'EB Garamond',
                ),
              ),
              const SizedBox(height: 24),
              const Text(
                'Team/Video Placeholder',
                style: TextStyle(
                  color: const Color(0xFFC9A84C),
                  fontSize: 24,
                  fontFamily: 'Cinzel',
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Placeholder for team information or project video.',
                style: TextStyle(
                  color: const Color(0xFFCCC5B8),
                  fontSize: 16,
                  fontFamily: 'EB Garamond',
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
