def create_plan_file(waypoints, drone_id, altitude_world=855, height=80):
    """
    Author: TG: @psyhhhh, email: diac.kusain@gmail.com
    """
    # Plan structure in JSON format
    plan_structure = {
        "fileType": "Plan",
        "geoFence": {
            "circles": [],
            "polygons": [],
            "version": 2
        },
        "groundStation": "QGroundControl",
        "mission": {
            "cruiseSpeed": 15,
            "firmwareType": 12,
            "globalPlanAltitudeMode": 1,
            "hoverSpeed": 5,
            "items": [],
            "plannedHomePosition": (waypoints[0][0], waypoints[0][1], altitude_world),
            "vehicleType": 2,
            "version": 2
        },
        "rallyPoints": {
            "points": [],
            "version": 2
        },
        "version": 1
    }

    # Add waypoints to the mission
    for i, point in enumerate(waypoints):
        altitude_mode = 0 if i > 0 else None
        command = 16 if i > 0 else 530  # Command 16 for regular points, 530 for home point
        if i == 1:
            command = 22  # Command 22 for second point
        frame = 3 if i > 0 else 2  # Frame 3 for all points except home point
        mission_item = {
            "AMSLAltAboveTerrain": None,
            "Altitude": height,
            "AltitudeMode": altitude_mode,
            "autoContinue": True,
            "command": command,
            "doJumpId": i + 1,
            "frame": frame,
            "params": [0, 0 if i > 0 else 2, 0, None, point[0], point[1], 50],
            "type": "SimpleItem"
        }
        if i == 0:
            mission_item = {
                "AMSLAltAboveTerrain": None,
                "Altitude": height,
                "AltitudeMode": altitude_mode,
                "autoContinue": True,
                "command": command,
                "doJumpId": i + 1,
                "frame": frame,
                "params": [0, 0 if i > 0 else 2, None, None, None, None, None],
                "type": "SimpleItem"
            }
        plan_structure['mission']['items'].append(mission_item)

    return plan_structure
