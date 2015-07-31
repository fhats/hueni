from beautifulhue.api import Bridge


class HueConnectionException(Exception):
    pass


class HueManager(object):
    """Provides methods to control and encapsulates state related to the lights
    connected to a Philips Hue Bridge."""

    HUESERNAME = "hueni"
    CORE_ATTRS = ('xy', 'on', 'bri')

    def __init__(self, bridge_address):
        """Sets up the HueManager and connects to a bridge specified at the
        address in `bridge`."""

        self.bridge_address = bridge_address

    def connect(self):
        probe_bridge = lambda: bridge.config.get(dict(which="system"))['resource']

        bridge_device = dict(ip=self.bridge_address)
        bridge_user = dict(name=self.HUESERNAME)
        bridge = Bridge(device=bridge_device, user=bridge_user)

        probe_response = probe_bridge()
        if 'lights' in probe_response:
            print "Connected to bridge"
        else:
            if probe_response[0]['error']['type'] == 1:
                self._create_bridge_config(bridge)
                self.connect()

        self.bridge = bridge

    def _create_bridge_config(self, bridge):
        # TODO: Get rid of stdout prints within this fcn
        created = False
        print 'Press the button on the Hue bridge'
        while not created:
            resource = {'user':{'devicetype': self.HUESERNAME, 'name': self.HUESERNAME}}
            response = bridge.config.create(resource)['resource']
            if 'error' in response[0]:
                if response[0]['error']['type'] != 101:
                    raise HueConnectionException("Unhandled error creating configuration on the Hue:\n%s" % response)
            else:
                created = True
        return created

