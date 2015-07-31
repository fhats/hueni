from contextlib import contextmanager
from copy import deepcopy

import mock
import pytest

from hueni.hue_manager import HueManager, HueConnectionException


class HueManagerTestCase(object):
    @contextmanager
    def mock_bridge(self):
        with mock.patch("hueni.hue_manager.Bridge") as mock_bridge_cls:
            mock_bridge_inst = mock.Mock()
            mock_bridge_cls.return_value = mock_bridge_inst

            yield mock_bridge_inst

    def create_mock_light(self, id_int=1, attrs=None):
        if not attrs:
            attrs = HueManager.CORE_ATTRS

        test_light = {
            "id": id_int,
            "state": {}
        }

        for attr in attrs:
            test_light['state'][attr] = 1

        return test_light


class TestCreateBridgeConfig(HueManagerTestCase):
    def test_create_bridge_config_happy(self):
        mock_successful_create = {"resource": [{"success": ""}]}

        mock_bridge = mock.Mock()
        mock_bridge.config.create = mock.Mock(return_value=mock_successful_create)

        test_bridge_address = "256.256.256.256"

        manager = HueManager(test_bridge_address)
        create_result = manager._create_bridge_config(mock_bridge)

        assert create_result

    def test_create_bridge_config_error(self):
        mock_unsuccessful_create = {"resource": [{"error": {"type": 900}}]}

        mock_bridge = mock.Mock()
        mock_bridge.config.create = mock.Mock(return_value=mock_unsuccessful_create)

        test_bridge_address = "256.256.256.256"

        manager = HueManager(test_bridge_address)
        with pytest.raises(HueConnectionException):
            create_result = manager._create_bridge_config(mock_bridge)

    def test_create_bridge_retries_on_error_101(self):
        mock_unsuccessful_create = {"resource": [{"error": {"type": 101}}]}
        mock_successful_create = {"resource": [{"success": ""}]}
        return_pattern = (mock_unsuccessful_create, mock_successful_create)

        mock_bridge = mock.Mock()
        mock_bridge.config.create = mock.Mock(side_effect=return_pattern)

        test_bridge_address = "256.256.256.256"
        manager = HueManager(test_bridge_address)
        create_result = manager._create_bridge_config(mock_bridge)

        assert create_result


class TestConnect(HueManagerTestCase):

    def test_connect_success(self):
        test_bridge_address = "256.256.256.256"
        with self.mock_bridge() as mock_bridge:
            mock_rv = {"resource": {"lights": ""}}
            mock_bridge.config.get.return_value = mock_rv

            manager = HueManager(test_bridge_address)
            manager.connect()

            assert manager.bridge == mock_bridge
            mock_bridge.config.get.assert_called_once_with({
                "which": "system"
            })

    def test_connect_recurse_once(self):
        test_bridge_address = "256.256.256.256"
        with self.mock_bridge() as mock_bridge:
            mock_rv = [
                {"resource": [{"error": {"type": 1}}]},
                {"resource": {"lights": ""}}
            ]
            mock_bridge.config.get.side_effect = mock_rv

            mock_bridge.config.create.return_value = {"resource": [""]}

            manager = HueManager(test_bridge_address)
            manager.connect()

            assert manager.bridge == mock_bridge
            assert mock_bridge.config.create.called


class TestSerializeLightState(HueManagerTestCase):
    def test_serializes_exactly_attrs(self):
        hm = HueManager("256.256.256.256")
        test_light = self.create_mock_light()
        assert test_light['state'] == hm._serialize_light_state(test_light)

    def test_serializes_fewer_attrs(self):
        hm = HueManager("256.256.256.256")
        test_light = self.create_mock_light(attrs=hm.CORE_ATTRS[:1])
        assert test_light['state'] == hm._serialize_light_state(test_light)

    def test_serializes_subset_attrs(self):
        hm = HueManager("256.256.256.256")
        test_light = self.create_mock_light()
        test_light['state']['some_other_unrelated_thing'] = "value"

        expected_value = {}
        for attr in hm.CORE_ATTRS:
            expected_value[attr] = 1
        assert expected_value == hm._serialize_light_state(test_light)


class TestStoreLightState(HueManagerTestCase):
    def test_store_light_state(self):
        light_one = self.create_mock_light(id_int=1)
        light_two = self.create_mock_light(id_int=2)

        mock_lights = {
            "resource": [light_one, light_two]
        }

        with self.mock_bridge() as mock_bridge:
            mock_bridge.light.get.return_value = mock_lights

            hm = HueManager("256.256.256.256")
            hm.bridge = mock_bridge
            hm.store_light_state()

        assert hm.natural_light_state[1] == light_one['state']
        assert hm.natural_light_state[2] == light_two['state']


class TestTriggerLights(HueManagerTestCase):
    def _make_mock_lights(self):
        mock_light_one = self.create_mock_light(id_int=1)
        mock_light_two = self.create_mock_light(id_int=2)
        return mock_light_one, mock_light_two

    def _make_lights_with_settings(self):
        mock_one, mock_two = self._make_mock_lights()
        lights_with_settings = {}
        lights_with_settings[1] = mock_one['state']
        lights_with_settings[2] = mock_two['state']

        return lights_with_settings

    def _make_expected_calls(self):
        mock_one, mock_two = self._make_mock_lights()
        expected_first_call = {
            "which": 1,
            "data": {
                "state": deepcopy(mock_one['state'])
            }
        }
        expected_second_call = {
            "which": 2,
            "data": {
                "state": deepcopy(mock_two['state'])
            }
        }
        expected_first_call['data']['state']['on'] = True
        expected_second_call['data']['state']['on'] = True
        expected_first_call['data']['state']['transitiontime'] = HueManager.DEFAULT_TRANSITIONTIME
        expected_second_call['data']['state']['transitiontime'] = HueManager.DEFAULT_TRANSITIONTIME

        return expected_first_call, expected_second_call

    def test_trigger_lights(self):
        lights_with_settings = self._make_lights_with_settings()
        expected_first_call, expected_second_call = self._make_expected_calls()
        expected_calls = [mock.call(expected_first_call),
            mock.call(expected_second_call)]

        with self.mock_bridge() as mock_bridge:
            hm = HueManager("256.256.256.256")
            hm.bridge = mock_bridge

            hm.trigger_lights(lights_with_settings)
            mock_bridge.light.update.assert_has_calls(expected_calls)

    def test_trigger_lights_with_transitiontime(self):
        lights_with_settings = self._make_lights_with_settings()
        expected_first_call, expected_second_call = self._make_expected_calls()

        lights_with_settings[1]['transitiontime'] = 10
        expected_first_call['data']['state']['transitiontime'] = 10

        expected_calls = [mock.call(expected_first_call),
            mock.call(expected_second_call)]

        with self.mock_bridge() as mock_bridge:
            hm = HueManager("256.256.256.256")
            hm.bridge = mock_bridge

            hm.trigger_lights(lights_with_settings)
            mock_bridge.light.update.assert_has_calls(expected_calls)

    def test_trigger_lights_forces_on(self):
        lights_with_settings = self._make_lights_with_settings()
        expected_first_call, expected_second_call = self._make_expected_calls()

        lights_with_settings[1]['on'] = False
        expected_first_call['data']['state']['on'] = True

        expected_calls = [mock.call(expected_first_call),
            mock.call(expected_second_call)]

        with self.mock_bridge() as mock_bridge:
            hm = HueManager("256.256.256.256")
            hm.bridge = mock_bridge

            hm.trigger_lights(lights_with_settings)
            mock_bridge.light.update.assert_has_calls(expected_calls)


class TestResetLight(HueManagerTestCase):
    def test_reset_light_shortcuts_when_same(self):
        mock_light = self.create_mock_light(id_int=1)
        with self.mock_bridge() as mock_bridge:
            mock_bridge.light.get.return_value = {
                "resource": mock_light
            }
            hm = HueManager("256.256.256.256")
            hm.bridge = mock_bridge

            hm.natural_light_state[1] = hm._serialize_light_state(mock_light)
            hm.reset_light(1)

            mock_bridge.light.update.assert_not_called()

    def test_reset_light(self):
        mock_light = self.create_mock_light(id_int=1)
        with self.mock_bridge() as mock_bridge:
            mock_bridge.light.get.return_value = {
                "resource": mock_light
            }
            hm = HueManager("256.256.256.256")
            hm.bridge = mock_bridge

            old_light_state = {
                "xy": 7,
                "bri": 5
            }

            hm.natural_light_state[1] = old_light_state

            hm.reset_light(1)

            expected_args = {
                "which": 1,
                "data": {
                    "state": old_light_state
                }
            }
            expected_args["data"]["state"]["transitiontime"] = 1

            mock_bridge.light.update.assert_called_once_with(expected_args)
