from collections import defaultdict

from beautifulhue.api import Bridge


class HueConnectionException(Exception):
    pass


class HueManager(object):
    """Provides methods to control and encapsulates state related to the lights
    connected to a Philips Hue Bridge."""

    CORE_ATTRS = ('xy', 'on', 'bri')
    DEFAULT_TRANSITIONTIME = 4
    HUESERNAME = "hueni"

    def __init__(self, bridge_address):
        """Sets up the HueManager and connects to a bridge specified at the
        address in `bridge`."""

        self.bridge_address = bridge_address

        self.natural_light_state = defaultdict(dict)

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

    def list_lights(self):
        return self.bridge.light.get(dict(which="all"))['resource']

    def reset_light(self, light_id):
        natural_state = self.natural_light_state[light_id]

        # First, figure out if we can skip this request
        current_state = self.bridge.light.get(dict(which=light_id))['resource']
        if self._serialize_light_state(current_state) == self.natural_light_state[light_id]:
            return

        # TODO: this can probably be DRY'd with the similar code in trigger_lights
        update_req = {
            "which": light_id,
            "data": {
                "state": self.natural_light_state[light_id]
            }
        }
        if 'transitiontime' not in update_req['data']['state']:
            update_req['data']['state']['transitiontime'] = 1
        print "Resetting light %s to %s" % (light_id, self.natural_light_state[light_id])
        self.bridge.light.update(update_req)

    def store_light_state(self):
        lights = self.list_lights()

        for light in lights:
            desired = self._serialize_light_state(light)
            self.natural_light_state[light['id']] = desired

    def trigger_lights(self, lights_with_settings):
        for light_id, light_settings in lights_with_settings.iteritems():
            update_req = {
                "which": light_id,
                "data": {
                    "state": light_settings
                }
            }
            update_req['data']['state']['on'] = True
            if 'transitiontime' not in update_req['data']['state']:
                update_req['data']['state']['transitiontime'] = self.DEFAULT_TRANSITIONTIME
            print "Setting light %s to %s" % (light_id, light_settings)
            self.bridge.light.update(update_req)

    def _serialize_light_state(self, light):
        return dict((x,y)
            for x,y in light['state'].iteritems()
            if x in self.CORE_ATTRS)

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

