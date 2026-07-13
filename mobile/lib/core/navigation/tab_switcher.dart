/// Lets a screen nested inside [AppShell]'s `IndexedStack` (e.g. Home's
/// "Find charging near you" button) switch bottom-nav tabs programmatically,
/// without giving every screen a direct reference to `AppShell`'s state.
class TabSwitcher {
  void Function(int index)? _handler;

  void attach(void Function(int index) handler) => _handler = handler;

  void switchTo(int index) => _handler?.call(index);
}
