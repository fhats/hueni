#!/usr/bin/python
from collections import defaultdict
from datetime import datetime, timedelta
from optparse import OptionParser
import sys
import time

from beautifulhue.api import Bridge
from fiveoneone.agency import Agency
from fiveoneone.route import Route
from fiveoneone.stop import Stop
from humanfriendly import parse_timespan
import yaml


HUESERNAME = "hueni-test"
CORE_ATTRS = ('xy', 'on', 'bri')

natural_light_state = {}


def get_bridge(options):
    def create_config():
        created = False
        print 'Press the button on the Hue bridge'
        while not created:
            resource = {'user':{'devicetype': HUESERNAME, 'name': HUESERNAME}}
            response = bridge.config.create(resource)['resource']
            if 'error' in response[0]:
                if response[0]['error']['type'] != 101:
                    print 'Unhandled error creating configuration on the Hue'
                    sys.exit(response)
            else:
                created = True

    probe_bridge = lambda: bridge.config.get(dict(which="system"))['resource']

    bridge_device = dict(ip=options.bridge)
    bridge_user = dict(name=HUESERNAME)
    bridge = Bridge(device=bridge_device, user=bridge_user)

    probe_response = probe_bridge()
    if 'lights' in probe_response:
        print "Connected to bridge"
    else:
        if probe_response[0]['error']['type'] == 1:
            create_config()
            bridge = get_bridge(options)

    return bridge


def collect_options():
    parser = OptionParser()
    parser.add_option("-b", "--bridge", help="The IP of the bridge to connect to")
    parser.add_option("-d", "--duration", type="str", default="", help="How long to run Hueni for")
    parser.add_option("-i", "--interval", type="int", default=15, help="How often to check for departures")
    parser.add_option("-t", "--token", help="A file containing a 511 API token")
    parser.add_option("--list-lights", action="store_true", help="Dump all the known lights")
    parser.add_option("--list-routes", action="store_true", help="Dump all monitored routes")
    parser.add_option("--list-stops",  default=False, help="Dump stops along a specified route")
    options, args = parser.parse_args()

    if options.list_lights:
        if not options.bridge:
            parser.error("You must specify a bridge to connect to")

        lights = list_lights(get_bridge(options))['resource']
        if lights:
            print "ID\tName"
            for light in lights:
                print "%d\t%s" % (light['id'], light['name'])
        else:
            print "No lights found."
        sys.exit(0)

    if options.list_routes:
        if not options.token:
            parser.error("You must supply a 511 API token!")

        token = load_config(options.token)

        print "Code\tName"
        for route in list_routes(token):
            print "%s\t%s" % (route.code, route.name)
        sys.exit(0)

    if options.list_stops:
        if not options.token:
            parser.error("You must supply a 511 API token!")

        token = load_config(options.token)

        print "Direction\tCode\tStop"
        for direction, stop in list_stops(token, options.list_stops):
            print "%s\t%s\t%s" % (direction.ljust(9), stop.code, stop.name)

        sys.exit(0)

    if not args or len(args) > 1:
        parser.error("You must specify a single configuration!")

    if not options.bridge:
        parser.error("You must specify a bridge to connect to")

    if not options.token:
        parser.error("You must supply a 511 API token!")

    if options.duration:
        options.duration = parse_timespan(options.duration)

    config_file = args[0]
    config = load_config(config_file)

    token = load_config(options.token)

    return options, config, token


def load_config(config_file):
    with open(config_file) as f:
        return yaml.load(f.read())


def load_token(token_file):
    with open(token_file) as f:
        return f.read().strip()


def list_lights(bridge):
    return bridge.light.get(dict(which="all"))


def list_routes(muni_token):
    agencies = Agency.agencies(muni_token)
    for agency in agencies:
        for route in agency.routes():
            # Only support SF-MUNI for right now
            if route.agency == "SFMTA":
                yield route


def list_stops(muni_token, route_name):
    for route in list_routes(muni_token):
        if str(route.code) == route_name:
            for direction in (route.INBOUND, route.OUTBOUND):
                for stop in route.stops(direction):
                    yield (direction, stop)


def store_light_state(bridge, *light_ids):
    if not light_ids:
        lights = bridge.light.get(dict(which='all'))['resource']

    for light in lights:
        desired = dict((x,y) for x,y in light['state'].iteritems() if x in CORE_ATTRS)
        natural_light_state[light['id']] = desired


def preprocess_config(muni_token, config):
    known_routes = {}
    for route in list_routes(muni_token):
        known_routes[str(route.code)] = route

    for stop_id, stop_config in config['stops'].iteritems():
        for route_id, route_config in stop_config.iteritems():
            config['stops'][stop_id][route_id]['route'] = known_routes[str(route_id)]

    return config


def process_departures(departure, bridge, route_config):
    triggered_rules = []
    for time in departure.times:
        time = int(time)
        for rule in route_config['rules']:
            if time <= int(rule['start']) and time > int(rule['end']):
                triggered_rules.append(rule)
    return triggered_rules


def trigger_lights(bridge, lights):
    for light_id, light_settings in lights.iteritems():
        update_req = {
            "which": light_id,
            "data": {
                "state": light_settings
            }
        }
        update_req['data']['state']['on'] = True
        if 'transitiontime' not in update_req['data']['state']:
            update_req['data']['state']['transitiontime'] = 4
        print "Setting light %s to %s" % (light_id, light_settings)
        bridge.light.update(update_req)


def reset_light(bridge, light_id):
    natural_state = natural_light_state[light_id]

    # First, figure out if we can skip this request
    current_state = bridge.light.get(dict(which=light_id))['resource']['state']
    if all([current_state[x] == natural_state[x] for x in CORE_ATTRS]):
        return

    update_req = {
        "which": light_id,
        "data": {
            "state": natural_light_state[light_id]
        }
    }
    if 'transitiontime' not in update_req['data']['state']:
        update_req['data']['state']['transitiontime'] = 1
    print "Resetting light %s to %s" % (light_id, natural_light_state[light_id])
    bridge.light.update(update_req)


def colate_lights(triggered_rules):
    rules_per_light = defaultdict(list)
    for rule in triggered_rules:
        for light_id, light_state in rule['lights'].iteritems():
            rules_per_light[light_id].append(light_state)

    for light_id, light_states in rules_per_light.iteritems():
        if config['effects']['merge']:
            merged_state = {}
            avg_state = defaultdict(lambda: defaultdict(int))
            for light_state in light_states:
                for light_attr, light_val in light_state.iteritems():
                    avg_state[light_attr]['sum'] += light_val
                    avg_state[light_attr]['count'] += 1
            for light_attr, avg_info in avg_state.iteritems():
                merged_state[light_attr] = avg_info['sum'] / avg_info['count']
            rules_per_light[light_id] = merged_state
        else:
            rules_per_light[light_id] = light_states[-1]

    return rules_per_light


def daemon_loop(config, muni_token, bridge):
    triggered_rules = []

    for stop_id, stop_config in config['stops'].iteritems():
        stop = Stop(muni_token, "", stop_id)

        for route_id, route_config in stop_config.iteritems():
            departure = stop.next_departures(route_id, route_config['direction'])
            print "%s - %s" % (route_id, departure.times)
            departure_rules_triggered = process_departures(departure, bridge, route_config)
            triggered_rules.extend(departure_rules_triggered)

    desired_light_states = colate_lights(triggered_rules)

    trigger_lights(bridge, desired_light_states)

    triggered_lights = set()
    for rule in triggered_rules:
        triggered_lights.update(rule['lights'].keys())

    for light_id in natural_light_state.iterkeys():
        if light_id not in triggered_lights:
            reset_light(bridge, light_id)

    return False


def do_quit(bridge):
    for light_id in natural_light_state.iterkeys():
        reset_light(bridge, light_id)


if __name__ == "__main__":
    options, config, token = collect_options()

    bridge = get_bridge(options)

    config = preprocess_config(token, config)

    store_light_state(bridge)

    start_time = datetime.now()

    if options.duration:
        print "Running for %d seconds" % options.duration

    should_quit = False
    while not should_quit:
        try:
            should_quit = daemon_loop(config, token, bridge)
            if should_quit:
                break
            else:
                time.sleep(options.interval)

            if options.duration:
                now = datetime.now()
                duration_delta = timedelta(seconds=options.duration)
                should_quit = now > (start_time + duration_delta)

        except KeyboardInterrupt:
            should_quit = True
        except Exception:
            should_quit = True
            do_quit(bridge)
            raise

    # Quit here
    do_quit(bridge)
