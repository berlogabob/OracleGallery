import 'package:flutter/material.dart';

import '../widgets/oracle_primitives.dart';

class AboutPage extends StatelessWidget {
  const AboutPage({super.key});

  @override
  Widget build(BuildContext context) {
    return OraclePage(
      children: const [
        OracleSection(
          label: 'Project',
          title: 'The oracle listens, measures instability, and leaves a mark.',
          child: Text(
            'Each visitor creates a short local session. The system publishes only the safe public receipt: the generated SVG mark, the receipt text, and the QR route back to this gallery.',
          ),
        ),
        OracleSection(
          label: 'Process',
          title: 'TouchDesigner produces the folder; Python publishes; the plotter draws.',
          child: Text(
            'The public web app is read-only. It never writes sessions, uploads files, or controls the plotter. Production decisions stay in the local operator GUI and the Python uploader/plotter stack.',
          ),
        ),
        OracleSection(
          label: 'Privacy',
          title: 'No visitor photos, audio, or transcripts are shown here.',
          child: Text(
            'The gallery displays the public mark and the edited receipt fields only. Raw session material remains outside the public Firebase contract.',
          ),
        ),
      ],
    );
  }
}
