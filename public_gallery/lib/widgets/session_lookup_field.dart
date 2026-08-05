import 'package:flutter/material.dart';

/// Shared session-ID lookup control: a text field plus a "Find" button
/// that stack vertically below a width breakpoint and sit in a row above
/// it. Used on the home page hero and the cloth page toolbar, which only
/// differ in field label and optional supporting copy.
class SessionLookupField extends StatelessWidget {
  const SessionLookupField({
    super.key,
    required this.controller,
    required this.onLookup,
    required this.labelText,
    this.supportingText,
  });

  final TextEditingController controller;
  final ValueChanged<String> onLookup;
  final String labelText;
  final String? supportingText;

  static const _breakpoint = 560.0;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < _breakpoint;
        final input = TextField(
          controller: controller,
          decoration: InputDecoration(
            labelText: labelText,
            hintText: '20260428_183129',
          ),
          onSubmitted: onLookup,
        );
        final button = FilledButton(
          onPressed: () => onLookup(controller.text),
          child: const Text('Find'),
        );
        final field = compact
            ? Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [input, const SizedBox(height: 12), button],
              )
            : Row(
                children: [
                  Expanded(child: input),
                  const SizedBox(width: 12),
                  button,
                ],
              );
        final supporting = supportingText;
        if (supporting == null) {
          return field;
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            field,
            const SizedBox(height: 10),
            Text(supporting, style: Theme.of(context).textTheme.bodyMedium),
          ],
        );
      },
    );
  }
}
