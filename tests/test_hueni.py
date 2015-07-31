import mock

from hueni import hueni


class HueniTestCase(object):
    pass


class TestListRoutes(HueniTestCase):
    def test_list_routes(self):
        mock_muni_token = mock.sentinel.muni_token
        with mock.patch("hueni.hueni.Agency") as mock_agency:
            mock_sfmta = mock.Mock()
            mock_bart = mock.Mock()
            mock_43 = mock.Mock()
            mock_43.agency = "SF-MUNI"
            mock_daly_city = mock.Mock()
            mock_daly_city.agency = "BART"

            mock_sfmta.routes.return_value = (
                mock_43,
            )
            mock_bart.routes.return_value = (
                mock_daly_city,
            )
            agency_list = (
                mock_sfmta,
                mock_bart,
            )
            mock_agency.agencies.return_value = agency_list

            for route in hueni.list_routes(mock_muni_token):
                assert route.agency in hueni.USED_AGENCIES


class TestProcessDepartures(HueniTestCase):
    def test_process_departures(self):
        mock_departure = mock.Mock()
        mock_departure.times = (1, 4, 9)

        mock_config = {
            "rules": [
                {
                    "start": 1,
                    "end": 0
                },
                {
                    "start": 5,
                    "end": 3
                }
            ]
        }

        triggered_rules = hueni.process_departures(mock_departure, mock_config)

        assert triggered_rules == mock_config["rules"]

