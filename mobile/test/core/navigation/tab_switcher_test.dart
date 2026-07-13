import 'package:evagg_driver/core/navigation/tab_switcher.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('calls the attached handler with the requested index', () {
    final switcher = TabSwitcher();
    final received = <int>[];
    switcher.attach(received.add);

    switcher.switchTo(2);
    switcher.switchTo(0);

    expect(received, [2, 0]);
  });

  test('switchTo before attach is a no-op', () {
    final switcher = TabSwitcher();
    expect(() => switcher.switchTo(1), returnsNormally);
  });
}
