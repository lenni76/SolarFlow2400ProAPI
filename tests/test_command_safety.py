"""Run the complete coordinator against an asynchronous simulated device.

Exercise service outcomes, cache freshness, cancellation and failed restoration.
No network, device writes or full Home Assistant runtime are used.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from copy import deepcopy
from types import SimpleNamespace

import test_device_links as shared


class HomeAssistantError(Exception):
    pass


class UpdateFailed(Exception):
    pass


class DataCoordinator:
    @classmethod
    def __class_getitem__(cls, _):
        return cls

    def __init__(self, hass, *, config_entry, **kwargs):
        self.hass = hass
        self.config_entry = config_entry
        self.data = None
        self.last_update_success = True
        self.notifications = []

    def async_update_listeners(self):
        d = self.diagnostics
        self.notifications.append((d.status, d.command_success, d.last_reported_value))

    def async_set_updated_data(self, data):
        self.data = data
        self.last_update_success = True
        self.async_update_listeners()

    async def async_request_refresh(self):
        try:
            self.async_set_updated_data(await self._async_update_data())
        except UpdateFailed:
            self.last_update_success = False
            raise


class SimulatedDevice:
    def __init__(self, error_type):
        self.error_type = error_type
        self.host = "192.0.2.1"
        self.properties = {
            "outputLimit": 200,
            "inputLimit": 0,
            "inverseMaxPower": 1000,
            "chargeMaxLimit": 2400,
            "acMode": 2,
            "electricLevel": 50,
            "outputHomePower": 200,
            "is_error": 0,
            "gridReverse": 2,
        }
        self.serial = "HUB-TEST"
        self.writes = []
        self.read_count = 0
        self.accept_power_at = 1
        self.power_writes = 0
        self.fail_writes = set()
        self.apply_then_fail = set()
        self.ignore_restore = False
        self.fail_reads = False

    async def async_get_report(self):
        self.read_count += 1
        if self.fail_reads:
            raise self.error_type("simulierter Lesefehler")
        return {"sn": self.serial, "properties": deepcopy(self.properties)}

    async def async_write_property(self, serial, key, value):
        assert serial == "HUB-TEST"
        self.writes.append((key, value))
        number = len(self.writes)
        if number in self.fail_writes:
            raise self.error_type("simulierter Schreibfehler")
        if key in {"outputLimit", "inputLimit"}:
            self.power_writes += 1
            if self.power_writes >= self.accept_power_at:
                self.properties[key] = value
        elif not (key == "acMode" and value == 2 and self.ignore_restore):
            self.properties[key] = value
        if number in self.apply_then_fail:
            raise self.error_type("Antwort nach Anwendung ausgeblieben")
        return {}


class CommandSafetyTests(shared.IntegrationTestCase):
    def load(self, name):
        spec = importlib.util.spec_from_file_location(
            f"{shared.PACKAGE}.{name}", shared.SOURCE / f"{name}.py"
        )
        loaded = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = loaded
        spec.loader.exec_module(loaded)
        return loaded

    async def asyncSetUp(self):
        self.clock = 100.0
        self.sleeps = []
        sys.modules["homeassistant.config_entries"] = shared.module(
            "homeassistant.config_entries", ConfigEntry=shared.Entry
        )
        sys.modules["homeassistant.exceptions"] = shared.module(
            "homeassistant.exceptions", HomeAssistantError=HomeAssistantError
        )
        sys.modules["homeassistant.helpers.aiohttp_client"] = shared.module(
            "homeassistant.helpers.aiohttp_client",
            async_get_clientsession=lambda hass: None,
        )
        sys.modules[
            "homeassistant.helpers.update_coordinator"
        ].DataUpdateCoordinator = DataCoordinator
        sys.modules[
            "homeassistant.helpers.update_coordinator"
        ].UpdateFailed = UpdateFailed
        self.api_module = self.load("api")
        self.module = self.load("coordinator")
        self.module.monotonic = lambda: self.clock

        async def no_sleep(seconds):
            self.sleeps.append(seconds)

        self.no_sleep = no_sleep
        self.module.asyncio = SimpleNamespace(
            Lock=asyncio.Lock,
            CancelledError=asyncio.CancelledError,
            sleep=no_sleep,
            create_task=asyncio.create_task,
            shield=asyncio.shield,
        )
        entry = shared.Entry("entry-a")
        entry.options = {}
        self.coordinator = self.module.ZendureCoordinator(self.hass(), entry)
        self.device = SimulatedDevice(self.api_module.ZendureApiError)
        self.coordinator.api = self.device
        await self.refresh()

    async def refresh(self):
        await self.coordinator.async_request_refresh()

    async def write(self, value=500, key="outputLimit"):
        await self.coordinator.async_write_property(key, value)

    async def test_duplicate_fresh_confirmed_value_is_skipped_without_sleep_or_post(
        self,
    ):
        await self.write(200)
        self.assertEqual(self.device.writes, [])
        self.assertEqual(self.sleeps, [])
        self.assertEqual(self.coordinator.diagnostics.skipped_write_count, 1)
        self.assertTrue(self.coordinator.diagnostics.command_success)
        self.assertIsNone(self.coordinator.diagnostics.last_write_at)

    async def test_zero_power_is_always_transmitted_in_both_directions(self):
        for key in ("outputLimit", "inputLimit"):
            for _ in range(2):
                await self.write(0, key)
        self.assertEqual(
            self.device.writes, [("outputLimit", 0)] * 2 + [("inputLimit", 0)] * 2
        )
        self.assertEqual(self.coordinator.diagnostics.skipped_write_count, 0)

    async def test_stale_duplicate_is_sent(self):
        self.clock += 6
        await self.write(200)
        self.assertEqual(self.device.writes, [("outputLimit", 200)])

    async def test_skip_can_be_disabled_in_options(self):
        self.coordinator.skip_unchanged = False
        await self.write(200)
        self.assertEqual(len(self.device.writes), 1)

    async def test_changed_lower_power_is_posted_before_any_validation_sleep(self):
        original = self.device.async_write_property

        async def observe(*args):
            self.assertEqual(self.sleeps, [])
            return await original(*args)

        self.device.async_write_property = observe
        await self.write(180)
        self.assertEqual(self.device.writes, [("outputLimit", 180)])

    async def test_previous_failed_command_disables_skip_on_next_request(self):
        self.coordinator.diagnostics.command_success = False
        await self.write(200)
        self.assertEqual(len(self.device.writes), 1)

    async def test_first_write_error_is_ha_error_and_finishes_diagnostics(self):
        self.device.fail_writes.add(1)
        with self.assertRaises(HomeAssistantError):
            await self.write()
        self.assertFalse(self.coordinator.diagnostics.command_success)
        self.assertEqual(self.coordinator.diagnostics.status, "Schreibfehler")
        self.assertEqual(self.coordinator.notifications[-1][1], False)
        self.assertIsNone(self.coordinator.report_age)

    async def test_ignored_command_returns_error_after_one_retry(self):
        self.device.accept_power_at = 99
        with self.assertRaises(HomeAssistantError):
            await self.write()
        d = self.coordinator.diagnostics
        self.assertEqual(len(self.device.writes), 2)
        self.assertFalse(d.command_success)
        self.assertEqual(d.status, "Befehl ignoriert")
        self.assertEqual((d.write_count, d.retry_count, d.total_retry_count), (2, 1, 1))

    async def test_retry_network_failure_is_also_wrapped_and_not_left_pending(self):
        self.device.accept_power_at = 99
        self.device.fail_writes.add(2)
        with self.assertRaises(HomeAssistantError):
            await self.write()
        self.assertEqual(self.coordinator.diagnostics.status, "Schreibfehler")
        self.assertFalse(self.coordinator.diagnostics.command_success)

    async def test_second_attempt_can_confirm_success(self):
        self.device.accept_power_at = 2
        await self.write()
        self.assertEqual(len(self.device.writes), 2)
        self.assertTrue(self.coordinator.diagnostics.command_success)

    async def test_confirmation_is_visible_in_the_notification_for_its_report(self):
        await self.write()
        reports = [item for item in self.coordinator.notifications if item[2] == 500]
        self.assertTrue(reports)
        self.assertTrue(all(item[1] is True for item in reports))

    async def test_validation_off_does_not_claim_confirmation(self):
        self.coordinator.command_validation = False
        self.device.accept_power_at = 99
        await self.write()
        self.assertIsNone(self.coordinator.diagnostics.command_success)
        self.assertEqual(self.coordinator.diagnostics.status, "Gesendet, nicht geprüft")
        self.assertEqual(len(self.device.writes), 1)

    async def test_failed_reads_cannot_confirm_or_populate_duplicate_cache(self):
        self.device.fail_reads = True
        with self.assertRaises(HomeAssistantError):
            await self.write()
        self.assertIsNone(self.coordinator.report_age)
        self.assertFalse(self.coordinator.diagnostics.command_success)

    async def test_report_from_other_serial_cannot_confirm_command(self):
        self.device.serial = "OTHER-HUB"
        with self.assertRaises(HomeAssistantError):
            await self.write()
        self.assertIsNone(self.coordinator.report_age)

    async def test_empty_properties_are_not_a_successful_refresh(self):
        self.device.properties = {}
        with self.assertRaises(UpdateFailed):
            await self.refresh()
        self.assertFalse(self.coordinator.last_update_success)

    async def test_successful_recovery_restores_mode_before_retrying_target(self):
        self.coordinator.auto_recovery = True
        self.device.accept_power_at = 3
        await self.write()
        self.assertEqual(
            self.device.writes,
            [
                ("outputLimit", 500),
                ("outputLimit", 500),
                ("acMode", 1),
                ("acMode", 2),
                ("outputLimit", 500),
            ],
        )
        d = self.coordinator.diagnostics
        self.assertTrue(d.command_success)
        self.assertFalse(d.recovery_active)
        self.assertFalse(d.recovery_restore_failed)
        self.assertEqual((d.write_count, d.recovery_write_count), (5, 3))

    async def test_recovery_never_toggles_ac_mode_for_zero_power(self):
        self.coordinator.auto_recovery = True
        self.device.accept_power_at = 99
        with self.assertRaises(HomeAssistantError):
            await self.write(0)
        self.assertTrue(all(key == "outputLimit" for key, _ in self.device.writes))

    async def test_recovery_without_confirmed_mode_does_not_toggle(self):
        self.coordinator.auto_recovery = True
        self.device.accept_power_at = 99
        self.device.properties.pop("acMode")
        with self.assertRaises(HomeAssistantError):
            await self.write()
        self.assertEqual(len(self.device.writes), 2)

    async def test_charging_recovery_never_enables_discharge(self):
        self.coordinator.auto_recovery = True
        self.device.accept_power_at = 99
        self.device.properties["acMode"] = 1
        with self.assertRaises(HomeAssistantError):
            await self.write(500, "inputLimit")
        self.assertTrue(all(key == "inputLimit" for key, _ in self.device.writes))

    async def test_recovery_requires_reported_reverse_flow_prohibition(self):
        self.coordinator.auto_recovery = True
        self.device.accept_power_at = 99
        self.device.properties["gridReverse"] = 1
        with self.assertRaises(HomeAssistantError):
            await self.write()
        self.assertEqual(len(self.device.writes), 2)
        self.assertEqual(self.device.properties["gridReverse"], 1)

    async def test_independently_cancelled_cleanup_propagates_without_spinning(self):
        async def cancelled_cleanup(mode):
            raise asyncio.CancelledError

        self.coordinator._restore_mode = cancelled_cleanup
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(self.coordinator._restore_shielded(2), 1)

    async def test_recovery_cooldown_returns_error_instead_of_false_success(self):
        self.coordinator.auto_recovery = True
        self.device.accept_power_at = 99
        self.coordinator.diagnostics.last_recovery_at = self.module.datetime.now(
            self.module.UTC
        )
        with self.assertRaises(HomeAssistantError):
            await self.write()
        self.assertEqual(len(self.device.writes), 2)
        self.assertEqual(self.coordinator.diagnostics.status, "Recovery gesperrt")

    async def test_ambiguous_toggle_error_still_restores_original_mode(self):
        self.coordinator.auto_recovery = True
        self.device.accept_power_at = 99
        self.device.apply_then_fail.add(3)
        with self.assertRaises(HomeAssistantError):
            await self.write()
        self.assertEqual(self.device.properties["acMode"], 2)
        self.assertEqual(self.device.writes[-1], ("acMode", 2))
        self.assertFalse(self.coordinator.diagnostics.recovery_restore_failed)

    async def test_restore_timeout_with_confirmed_readback_needs_no_extra_restore_post(
        self,
    ):
        self.coordinator.auto_recovery = True
        self.device.accept_power_at = 3
        self.device.apply_then_fail.add(4)
        await self.write()
        self.assertEqual(self.device.writes.count(("acMode", 2)), 1)
        self.assertTrue(self.coordinator.diagnostics.command_success)

    async def test_failed_restore_stays_visible_and_prevents_target_reapplication(self):
        self.coordinator.auto_recovery = True
        self.device.accept_power_at = 99
        self.device.ignore_restore = True
        with self.assertRaises(HomeAssistantError):
            await self.write()
        d = self.coordinator.diagnostics
        self.assertTrue(d.recovery_restore_failed)
        self.assertEqual(d.restore_mode, 2)
        self.assertEqual(self.device.properties["acMode"], 1)
        self.assertEqual(self.device.writes.count(("acMode", 2)), 2)
        self.assertEqual(self.device.power_writes, 2)
        self.assertEqual(self.coordinator.current_status, "AC-Modus unbestätigt")
        self.assertFalse(d.recovery_active)

    async def test_confirmed_original_mode_clears_alarm_but_keeps_command_failure(
        self,
    ):
        d = self.coordinator.diagnostics
        d.recovery_restore_failed, d.restore_mode, d.command_success = True, 2, False
        await self.refresh()
        self.assertFalse(d.recovery_restore_failed)
        self.assertFalse(d.command_success)
        self.assertEqual(self.coordinator.current_status, "Normal")

    async def test_cancellation_after_toggle_restores_mode_and_propagates_cancel(self):
        self.coordinator.auto_recovery = True
        self.device.accept_power_at = 99
        toggled = asyncio.Event()

        async def block_after_toggle(seconds):
            if seconds == 1 and self.device.properties["acMode"] == 1:
                toggled.set()
                await asyncio.Event().wait()

        self.module.asyncio.sleep = block_after_toggle
        task = asyncio.create_task(self.write())
        await asyncio.wait_for(toggled.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.device.properties["acMode"], 2)
        self.assertFalse(self.coordinator.diagnostics.recovery_active)
        self.assertFalse(self.coordinator.diagnostics.recovery_restore_failed)
        self.assertFalse(self.coordinator.diagnostics.command_success)
        self.assertFalse(self.coordinator._write_lock.locked())

    async def test_cancellation_during_restore_keeps_lock_until_cleanup_finishes(self):
        self.coordinator.auto_recovery = True
        self.device.accept_power_at = 3
        restoring, release = asyncio.Event(), asyncio.Event()

        async def pause_restore(seconds):
            if seconds == 1 and self.device.properties["acMode"] == 2:
                restoring.set()
                await release.wait()

        self.module.asyncio.sleep = pause_restore
        task = asyncio.create_task(self.write())
        await asyncio.wait_for(restoring.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        self.assertTrue(self.coordinator._write_lock.locked())
        self.assertFalse(task.done())
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.device.power_writes, 2)
        self.assertFalse(self.coordinator._write_lock.locked())

    async def test_current_health_is_independent_of_old_command_error(self):
        d = self.coordinator.diagnostics
        d.status, d.command_success = "Schreibfehler", False
        await self.refresh()
        self.assertEqual(self.coordinator.current_status, "Normal")
        self.assertEqual(d.status, "Schreibfehler")
        self.device.properties["is_error"] = 1
        await self.refresh()
        self.assertEqual(self.coordinator.current_status, "Gerätefehler")

    async def test_stale_data_never_claims_normal_health(self):
        self.clock += 61
        self.assertEqual(self.coordinator.current_status, "Gerätedaten veraltet")

    async def test_inflight_prewrite_report_cannot_create_fresh_duplicate_cache(self):
        original = self.device.async_get_report
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed_read():
            snapshot = await original()
            entered.set()
            await release.wait()
            return snapshot

        self.device.async_get_report = delayed_read
        task = asyncio.create_task(self.refresh())
        await asyncio.wait_for(entered.wait(), 1)
        self.device.async_get_report = original
        await self.write(500)
        self.coordinator.diagnostics.recovery_restore_failed = True
        self.coordinator.diagnostics.restore_mode = 2
        self.device.properties["acMode"] = 1
        release.set()
        with self.assertRaises(UpdateFailed):
            await task
        self.assertIsNone(self.coordinator.report_age)
        self.assertTrue(self.coordinator.diagnostics.recovery_restore_failed)
        self.assertEqual(self.coordinator.diagnostics.restore_mode, 2)
        await self.write(200)
        self.assertEqual(self.device.writes[-1], ("outputLimit", 200))

    def test_exact_comparison_does_not_treat_different_wire_values_as_equal(self):
        self.assertFalse(self.module._numbers_equal(200, 200.5))
        self.assertFalse(self.module._numbers_equal(float("nan"), float("nan")))
        self.assertFalse(self.module._numbers_equal(200, None))
