from contextlib import contextmanager

import mock
import pytest

from hueni.hue_manager import HueManager, HueConnectionException


class HueManagerTestCase:
    pass


class TestCreateBridgeConfig(HueManagerTestCase):
    def test_create_bridge_config_happy(self):
        mock_successful_create = {"resource": [{"success"}]}

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
        mock_successful_create = {"resource": [{"success"}]}
        return_pattern = (mock_unsuccessful_create, mock_successful_create)

        mock_bridge = mock.Mock()
        mock_bridge.config.create = mock.Mock(side_effect=return_pattern)

        test_bridge_address = "256.256.256.256"
        manager = HueManager(test_bridge_address)
        create_result = manager._create_bridge_config(mock_bridge)

        assert create_result


class TestConnect(HueManagerTestCase):
    @contextmanager
    def mock_bridge(self):
        with mock.patch("hueni.hue_manager.Bridge") as mock_bridge_cls:
            mock_bridge_inst = mock.Mock()
            mock_bridge_cls.return_value = mock_bridge_inst

            yield mock_bridge_inst

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
