from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from app.services import tray_customer_worker as worker

NOW = datetime(2026, 10, 13, 18, tzinfo=timezone.utc)


def test_catalog_advances_all_pages_and_enters_contact_phase(monkeypatch):
    catalog = Mock(return_value=False)
    monkeypatch.setattr(worker.tray_customer_sync, "catalog_page", catalog)
    instance = worker.TrayCustomerWorker()
    assert instance.advance('a', {'phase': 'catalog', 'next_page': 4}, NOW) == {'next_page': 8}
    assert sorted(call.args[1] for call in catalog.call_args_list) == [4, 5, 6, 7]
    catalog.return_value = True
    result = instance.advance('a', {'phase': 'catalog', 'next_page': 8}, NOW)
    assert result['phase'] == 'contacts'
    assert result['last_full_at'] == NOW.isoformat()


def test_midnight_incremental_scan_covers_both_days(monkeypatch):
    catalog = Mock(return_value=True)
    monkeypatch.setattr(worker.tray_customer_sync, "catalog_page", catalog)
    result = worker.TrayCustomerWorker().advance('a', {
        'phase': 'incremental', 'next_page': 1, 'scan_date': '2026-10-12'}, NOW)
    assert result == {'next_page': 1, 'scan_date': '2026-10-13'}
    catalog.assert_called_once_with('a', 1, modified='2026-10-12')


def test_no_pending_contacts_schedules_incremental_poll(monkeypatch):
    monkeypatch.setattr(worker.tray_customer_sync, 'hydrate_pending', lambda _: True)
    result = worker.TrayCustomerWorker().advance('a', {
        'phase': 'contacts', 'last_full_at': NOW.isoformat(), 'last_scan_at': NOW.isoformat()}, NOW)
    assert result['phase'] == 'idle'
    assert result['next_run_at'] == (NOW + timedelta(minutes=15)).isoformat()


def test_scans_continue_during_long_initial_contact_import(monkeypatch):
    hydrate = Mock()
    monkeypatch.setattr(worker.tray_customer_sync, 'hydrate_pending', hydrate)
    result = worker.TrayCustomerWorker().advance('a', {
        'phase': 'contacts', 'last_full_at': NOW.isoformat(),
        'last_scan_at': (NOW-timedelta(minutes=16)).isoformat()}, NOW)
    assert result['phase'] == 'incremental'
    hydrate.assert_not_called()
