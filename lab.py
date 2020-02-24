#!/usr/bin/env python3

from util import read_osm_data, great_circle_distance, to_local_kml_url

# NO ADDITIONAL IMPORTS!


ALLOWED_HIGHWAY_TYPES = {
    'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified',
    'residential', 'living_street', 'motorway_link', 'trunk_link',
    'primary_link', 'secondary_link', 'tertiary_link',
}


DEFAULT_SPEED_LIMIT_MPH = {
    'motorway': 60,
    'trunk': 45,
    'primary': 35,
    'secondary': 30,
    'residential': 25,
    'tertiary': 25,
    'unclassified': 25,
    'living_street': 10,
    'motorway_link': 30,
    'trunk_link': 30,
    'primary_link': 30,
    'secondary_link': 30,
    'tertiary_link': 25,
}


def build_auxiliary_structures(nodes_filename, ways_filename):
    """
    read data from nodes_filename, ways_filename using read_osm_data
    return a graph of adjacency nodes, as a dictionary
    {
        node1: {node2: speed-x, node3: speed-y, node9: speed-z,...}
        node2: {node1: speed-a, node4: speed-b,...}
        ,...
    }
    """
    graph = {}
    for raw_way in read_osm_data(ways_filename):
        if 'highway' in raw_way['tags'] and raw_way['tags']['highway'] in ALLOWED_HIGHWAY_TYPES: # relevant ways
            # speed limit property
            if 'maxspeed_mph' in raw_way['tags']: speed = raw_way['tags']['maxspeed_mph']
            else: speed = DEFAULT_SPEED_LIMIT_MPH[raw_way['tags']['highway']]
            for node1, node2 in zip(raw_way['nodes'], raw_way['nodes'][1:]):
                if node1 in graph and node2 in graph[node1]: # found higher-speed way for node1 -> node2
                    graph[node1][node2] = min(graph[node1][node2], speed)
                else:  graph.setdefault(node1, {})[node2] = speed
                if not ('oneway' in raw_way['tags'] and raw_way['tags']['oneway'] == 'yes'): # 2 way
                    if node2 in graph and node1 in graph[node2]: # found higher-speed way for node2 -> node1
                        graph[node2][node1] = min(graph[node2][node1], speed)
                    else: graph.setdefault(node2, {})[node1] = speed
            if ('oneway' in raw_way['tags'] and raw_way['tags']['oneway'] == 'yes'):
                # NOTE: dont forget, the zip(raw_way['nodes'], raw_way['nodes'][1:]) statement 
                # might skip adding the last node in way['nodes'] if it's a one-way way
                graph.setdefault(node2, {})
    for node in read_osm_data(nodes_filename):
        if node['id'] in graph:   # only nodes that appeared on some ways are considered
            graph[node['id']]['loc'] = (node['lat'], node['lon'])
    return graph
# a way = {'id': 8654227, 'nodes': [61692905, 61690629], 'tags': {'name': 'Homestead Road', 'lanes': '2', 'width': '12.2', 'source': 'massgis_import_v0.1_20071008144750', 'highway': 'residential', 'condition': 'fair', 'attribution': 'Office of Geographic and Environmental Information (MassGIS)', 'massgis:way_id': '191019'}}

def find_path(graph, loc1, loc2, short):
    def find_start_end(loc1, loc2):
        """
        Find start/end nodes near loc1/loc2, by iterating over a graph 
        of all valid nodes (those appeared on some ways); and find smallest great_circle_distance
        """
        start = end = None # start node, end node
        min_start_distance = min_end_distance = float('inf')
        for node_id in graph:
            node_loc = graph[node_id]['loc']
            distance_start = great_circle_distance(loc1, node_loc)
            distance_end = great_circle_distance(loc2, node_loc)
            if distance_start < min_start_distance:
                start, min_start_distance = node_id, distance_start
            if distance_end < min_end_distance:
                end, min_end_distance = node_id, distance_end
        return start, end
        
    start, end = find_start_end(loc1, loc2)

    # find shortest/fastest path from start to end, using uniform-cost search
    agenda = [(0, [start])] # list of tuples (cost, path)
    expanded = set()
    # pulled_agenda = 0 ## counter, comparison of using heuristic vs not-using-heuristic
    while agenda:
        # find lowest cost path currently in agenda || would be nice if i am allowed to import heapq
        # HEURISTIC
        if short: # use heuristic
            min_cost_so_far, min_index = float('inf'), None
            for i, (cost_heuristic, path) in enumerate(agenda):
                cost_heuristic += great_circle_distance(graph[path[-1]]['loc'], graph[end]['loc'])
                if cost_heuristic < min_cost_so_far:
                    min_cost_so_far, min_index = cost_heuristic, i
            path_cost, path = agenda.pop(min_index)
        else: # not use heuristic for find_fast_path
            path_cost, path = agenda.pop(min(range(len(agenda)), key= agenda.__getitem__))
        # pulled_agenda += 1
        terminal = path[-1]
        if terminal not in expanded:
            if terminal == end: # found the path, return list of tuples nodes locations: (lat, lon)
                #print(pulled_agenda)
                #return path
                return [graph[node_id]['loc'] for node_id in path]
            expanded.add(terminal)
            for adj in graph[terminal]:
                if adj not in expanded and adj in graph:
                    new_cost = great_circle_distance(graph[adj]['loc'], graph[terminal]['loc'])
                    if not short: # fastest path, calculate terminal->adj cost = dist/speed = time travel
                        new_cost /= graph[terminal][adj] # speed
                    agenda.append((path_cost + new_cost, path + [adj]))
    return None


def find_short_path(aux_structures, loc1, loc2):
    """
    Return the shortest path between the two locations
    Parameters:
        aux_structures: the result of calling build_auxiliary_structures
        loc1: tuple of 2 floats: (latitude, longitude), representing the start
              location
        loc2: tuple of 2 floats: (latitude, longitude), representing the end
              location
    Returns:
        a list of (latitude, longitude) tuples representing the shortest path
        (in terms of distance) from loc1 to loc2. return None if fail to find a path

    """
    return find_path(aux_structures, loc1, loc2, True)

def find_fast_path(aux_structures, loc1, loc2):
    """
    Return the shortest path between the two locations, in terms of expected
    time (taking into account speed limits).

    Parameters:
        aux_structures: the result of calling build_auxiliary_structures
        loc1: tuple of 2 floats: (latitude, longitude), representing the start
              location
        loc2: tuple of 2 floats: (latitude, longitude), representing the end
              location

    Returns:
        a list of (latitude, longitude) tuples representing the shortest path
        (in terms of time) from loc1 to loc2.
    """
    return find_path(aux_structures, loc1, loc2, False)


if __name__ == '__main__':
    # NODES
    #{'id': 61340445, 'lat': 42.31441, 'lon': -71.077542, 'tags': {'source': 'massgis_import_v0.1_20071008193615', 'created_by': 'JOSM', 'attribution': 'Office of Geographic and Environmental Information (MassGIS)'}}
    #{'id': 61340447, 'lat': 42.31451, 'lon': -71.091368, 'tags': {'source': 'massgis_import_v0.1_20071008193615', 'created_by': 'JOSM', 'attribution': 'Office of Geographic ^C': 'Office of Geographic and Environmental Information (MassGIS)'}}
    # WAYS
    # {'id': 8654227, 'nodes': [61692905, 61690629], 'tags': {'name': 'Homestead Road', 'lanes': '2', 'width': '12.2', 'source': 'massgis_import_v0.1_20071008144750', 'highway': 'residential', 'condition': 'fair', 'attribution': 'Office of Geographic and Environmental Information (MassGIS)', 'massgis:way_id': '191019'}}
    # {'id': 8654228, 'nodes': [61688632, 61695439], 'tags': {'name': 'Lakeview Street', 'lanes': '2', 'width': '12.2', 'highway': 'residential', 'surface': 'asphalt', 'condition': 'fair'}}

    # NodeURL = 'resources/cambridge.nodes'
    # WayURL = 'resources/cambridge.ways'

    # # totalnode = has_name = mitid = 0
    # # for node in read_osm_data(NodeURL):
    # #     totalnode += 1
    # #     if 'name' in node['tags']:
    # #         has_name += 1
    # #         if node['tags']['name'] == '77 Massachusetts Ave': mitid = node['id']
    # # print(totalnode, has_name, mitid)
    # totalways = oneway = 0
    # for way in read_osm_data(WayURL):
    #     totalways += 1
    #     if 'oneway' in way['tags'] and way['tags']['oneway'] == 'yes': oneway += 1
    # print(totalways, oneway)
    # path = []
    # for way in read_osm_data(midwestWayUrl):
    #     if way['id'] == 21705939:
    #         path = way['nodes']
    #         break
    # total_miles = 0
    # for n1, n2 in zip(path, path[1:]):
    #     loc1, loc2 = midwestNodes[n1], midwestNodes[n2]
    #     total_miles += great_circle_distance(loc1, loc2)
    # print(total_miles)
    # region = 'midwest'
    # print(nearest_node(nodeF, wayF, (41.4452463, -89.3161394)))

    # region = 'midwest'
    # nodeF, wayF = f'resources/{region}.nodes', f'resources/{region}.ways'
    # aux = build_auxiliary_structures(nodeF, wayF)
    # starbucksMemDrive = (42.358118, -71.114954)
    # stata = (42.361705, -71.090593)
    # aux = build_auxiliary_structures('resources/cambridge.nodes', 'resources/cambridge.ways')
    # print(to_local_kml_url(find_short_path(aux, starbucksMemDrive, stata)))

    # region = 'cambridge'
    # nodeF, wayF = f'resources/{region}.nodes', f'resources/{region}.ways'
    # aux = build_auxiliary_structures(nodeF, wayF)
    # find_short_path(aux, (42.3858, -71.0783), (42.5465, -71.1787))
    # NOTE: using heuristic = 47,609 pulls from agenda
    # no heristic = 386,255 pulls.

    region = 'mit'
    nodeF, wayF = f'resources/{region}.nodes', f'resources/{region}.ways'
    aux = build_auxiliary_structures(nodeF, wayF)
    # loc1 = (42.3575, -71.0952)
    # loc2 = (42.3602, -71.0911)
    # print("SHORT PATH ", find_short_path(aux, loc1, loc2))
    # print("FAST PATH ", find_fast_path(aux, loc1, loc2))


    loc1 = (42.3575, -71.0956) # 11 Parking Lot - end of a oneway and not on any other way
    loc2 = (42.3575, -71.0940) # 1
    print("SHORT PATH2 ", find_short_path(aux, loc1, loc2))

# SHORT PATH  [1, 10, 5, 6]
# FAST PATH  [1, 10, 5, 7, 8, 6]
# SHORT PATH  [(42.3575, -71.0952), (42.3582, -71.0931), (42.3592, -71.0932), (42.36, -71.0907)]
# FAST PATH  [(42.3575, -71.0952), (42.3582, -71.0931), (42.3592, -71.0932), (42.3601, -71.0952), (42.3612, -71.092), (42.36, -71.0907)]


    # region = 'midwest'
    # nodeF, wayF = f'resources/{region}.nodes', f'resources/{region}.ways'
    # aux = build_auxiliary_structures(nodeF, wayF)
    # loc1, loc2 = (41.375288, -89.459541), (41.452802, -89.443683)
    # print("SHORT PATH ", len(find_short_path(aux, loc1, loc2)))