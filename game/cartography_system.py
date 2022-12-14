import os
from itertools import cycle
import pyglet
import sys
import json

from . import ecs
from .settings import settings
from .assets import ASSETS
from .common import *
from .components import (
    PhysicsComponent,
    FlightPathComponent,
    MapComponent,
    Visual,
    GameVisualComponent,
    UIVisualComponent,
    CheckpointComponent,
    CollisionComponent,
)
from .ecs import *
from .vector import V2




class CartographySystem(System):
    def setup(self):
        self.subscribe("StartMapping", self.handle_start_mapping)
        self.subscribe("StopMapping", self.handle_stop_mapping)
        self.subscribe("LoadMap", self.handle_load_map)
        self.subscribe("ExitMap", self.clear_map)
        self.subscribe("StartPlacements", self.handle_start_placements)
        self.subscribe("StopPlacements", self.handle_stop_placements)
        self.subscribe("PlacementSelection", self.handle_placement_selection)
        self.subscribe("Place", self.handle_place)
        # Name, Mass, Collision Radius
        self.selections = [
            ("satellite", 5, 80),
            ("asteroid_small", 10, 60),
            ("asteroid_medium", 25, 100),
            ("asteroid_large", 50, 175),
            ("moon", 15, 56),
            ("red_planet", 100, 220),
            ("earth", 400, 500),
            ("dwarf_gas_planet", 40, 150),
            ("medium_gas_planet", 150, 240),
            ("gas_giant", 300, 500),
            ("black_hole", 1000, 332),
            ("checkpoint", None, 1),
            ("boost_powerup", None, None),
            ("slowdown", None, None),
            ("large_red_planet", 3000, 2000),
        ]

    def handle_start_mapping(self, **kwargs):
        map_entity = get_active_map_entity()
        map_ = map_entity["map"]
        map_.flight_path = []
        map_.mode = "mapping"

    def handle_stop_mapping(self, **kwargs):
        map_entity = get_active_map_entity()
        map_ = map_entity["map"]
        with open(os.path.join("maps", f"{map_.map_name}_path.json"), "w") as f:
            f.write(json.dumps(map_.flight_path, indent=2))
        map_.flight_path = []
        map_.mode = "freeplay"

    def handle_load_map(self, *, map_name, mode="racing", **kwargs):
        self.clear_map()
        map_entity_id = self.load_map(map_name)
        map_entity = Entity.find(map_entity_id)
        map_ = map_entity["map"]
        map_.mode = mode
        System.dispatch(
            event="MapLoaded",
            map_name=map_name,
            map_entity_id=map_entity_id,
        )

    def handle_start_placements(self, **kwargs):
        map_entity = get_active_map_entity()
        map_ = map_entity["map"]
        with open(os.path.join("maps", f"{map_.map_name}_objects.json"), "r") as f:
            data = f.read()
        map_.map_objects = json.loads(data)
        map_.mode = "editing"
        settings.GRAVITY = False

        entity = Entity()
        map_.edit_selection_id = entity.entity_id
        selection = self.selections[map_.edit_selection_index]
        label = pyglet.text.Label(
            selection[0], font_size=36, x=20, y=20, anchor_x="left", anchor_y="bottom"
        )
        entity.attach(
            UIVisualComponent(visuals=[Visual(kind="label", z_sort=0, value=label)])
        )

        # Load flight path data in so we can add checkpoints
        with open(os.path.join("maps", f"wip_path.json"), "r") as f:
            map_path_data = f.read()
        map_.flight_path = json.loads(map_path_data)

    def handle_stop_placements(self, **kwargs):
        settings.GRAVITY = True
        map_entity = get_active_map_entity()
        if not map_entity:
            return

        map_ = map_entity["map"]
        if not map_.mode == "editing":
            return

        map_.mode = "freeplay"

        with open(os.path.join("maps", f"{map_.map_name}_objects.json"), "w") as f:
            f.write(json.dumps(map_.map_objects, indent=2))

        with open(os.path.join("maps", f"{map_.map_name}_path.json"), "w") as f:
            f.write(json.dumps(map_.flight_path, indent=2))

        System.dispatch(event="LoadMap", map_name=map_.map_name, mode="freeplay")
        Entity.find(map_.edit_selection_id).destroy()

    def handle_place(self, *, position, map_entity_id, **kwargs):
        map_entity = Entity.find(map_entity_id)
        if not map_entity:
            return

        map_ = map_entity["map"]
        if not map_.mode == "editing":
            return

        object_name, mass, radius = self.selections[map_.edit_selection_index]
        if object_name == "checkpoint":
            points = [
                ((position - V2(p["x"], p["y"])).length_squared, p)
                for p in map_.flight_path
            ]
            closest_distance = min(x[0] for x in points)
            closest_point = [p for d, p in points if d == closest_distance][0]
            if "check_point" not in closest_point:
                closest_point["checkpoint"] = True

                point_index = map_.flight_path.index(closest_point)
                if point_index == 0:
                    p1 = map_.flight_path[point_index + 1]
                    p2 = map_.flight_path[point_index]
                else:
                    p1 = map_.flight_path[point_index]
                    p2 = map_.flight_path[point_index - 1]

                p1 = V2(p1["x"], p1["y"])
                p2 = V2(p2["x"], p2["y"])
                rotation = (p1 - p2).degrees - 90
                num_points = sum(1 for p in map_.flight_path if "checkpoint" in p)
                self.load_checkpoint(
                    V2(closest_point["x"], closest_point["y"]),
                    rotation,
                    num_points,
                    map_entity_id,
                )

        elif mass is not None and radius is not None:
            map_.map_objects.append(
                {"object": object_name, "x": position.x, "y": position.y}
            )
            self.load_object(object_name, position, mass, radius)

    def handle_placement_selection(self, *, direction, **kwargs):
        map_entity = get_active_map_entity()
        if not map_entity:
            return

        map_ = map_entity["map"]
        if not map_.mode == "editing":
            return

        if direction == "up":
            map_.edit_selection_index = (map_.edit_selection_index - 1) % len(
                self.selections
            )
        elif direction == "down":
            map_.edit_selection_index = (map_.edit_selection_index + 1) % len(
                self.selections
            )
        object_name, mass, radius = self.selections[map_.edit_selection_index]
        Entity.find(map_.edit_selection_id)["ui visual"].visuals[
            0
        ].value.text = object_name

    def update(self):
        map_entity = get_active_map_entity()
        if not map_entity:
            return

        map_ = map_entity["map"]

        if not map_.mode == "mapping":
            return

        entity = get_ship_entity()
        position = entity["physics"].position

        if len(map_.flight_path) == 0:
            map_.flight_path.append({"x": position.x, "y": position.y})

        # Calculate distance to from the last mapped point to see
        # if we have traveled far enough to warrant mapping another point
        last_point = map_.flight_path[-1]
        last_point = V2(last_point["x"], last_point["y"])
        distance = (last_point - position).length

        if distance > 50:
            map_.flight_path.append({"x": position.x, "y": position.y})

    def load_object(self, name, position, mass, radius):
        entity = create_sprite(position, 0, ASSETS[name])
        entity.attach(PhysicsComponent(position=position, mass=mass))
        entity.attach(CollisionComponent(circle_radius=radius))

    def load_checkpoint(self, position, rotation, cp_order, map_entity_id):
        cp = Entity()

        cp.attach(PhysicsComponent(position=position, rotation=rotation))
        #cp.attach(CollisionComponent(circle_radius=radius))

        top_cp_image = "checkpoint_top" if cp_order == 0 else "checkpoint_next_top"
        top_cp_sprite = pyglet.sprite.Sprite(
            ASSETS[top_cp_image], x=position.x, y=position.y
        )

        bottom_cp_image = (
            "checkpoint_bottom" if cp_order == 0 else "checkpoint_next_bottom"
        )
        bottom_cp_sprite = pyglet.sprite.Sprite(
            ASSETS[bottom_cp_image], x=position.x, y=position.y
        )

        top_cp_sprite.rotation = rotation
        bottom_cp_sprite.rotation = rotation

        cp.attach(
            GameVisualComponent(
                visuals=[
                    Visual(kind="sprite", z_sort=-9.0, value=top_cp_sprite),
                    Visual(kind="sprite", z_sort=-12.0, value=bottom_cp_sprite),
                ]
            )
        )

        cp.attach(
            UIVisualComponent(
                visuals=[
                    Visual(
                        kind="checkpoint arrow",
                        z_sort=1.0,
                        value=pyglet.sprite.Sprite(ASSETS["checkpoint_arrow"]),
                    )
                ]
            )
        )

        cp.attach(
            CheckpointComponent(
                next_image_bottom=ASSETS["checkpoint_bottom"],
                passed_image_bottom=ASSETS["checkpoint_passed_bottom"],
                next_image_top=ASSETS["checkpoint_top"],
                passed_image_top=ASSETS["checkpoint_passed_top"],
                finish_image_top=ASSETS["checkpoint_finish_top"],
                finish_image_bottom=ASSETS["checkpoint_finish_bottom"],
                cp_order=cp_order,
                map_entity_id=map_entity_id,
            )
        )

    def clear_map(self, **kwargs):
        old_maps = Entity.with_component("map")
        for old_map in old_maps:
            old_map["map"].is_active = False
            if old_map["map"].speedometer_id:
                Entity.find(old_map["map"].speedometer_id).destroy()
            old_map.destroy()

        ship_id = get_ship_entity().entity_id

        physics_entities = list(Entity.with_component("physics"))
        for entity in physics_entities:
            if entity.entity_id != ship_id:
                entity.destroy()

        for entity in Entity.with_component("flight path"):
            entity.destroy()

    def load_map(self, map_name):
        map_entity = Entity()
        map_entity.attach(MapComponent(map_name=map_name))
        map_ = map_entity['map']

        with open(os.path.join("maps", f"{map_name}_objects.json"), "r") as f:
            map_objects_data = f.read()
        map_objects = json.loads(map_objects_data)

        objects_with_selections = set(i for i, _, _ in self.selections)
        for item in map_objects:
            if item["object"] in objects_with_selections:
                object_name, mass, radius = [
                    s for s in self.selections if s[0] == item["object"]
                ][0]
                position = V2(item["x"], item["y"])
                self.load_object(object_name, position, mass, radius)
            elif item["object"] == 'tutorial text':
                tutorial_text = item['text']
                if tutorial_text == 'mouse_or_keys':
                    if settings.MOUSE_TURNING:
                        tutorial_text = 'Aim your ship with the mouse to turn'
                    else:
                        tutorial_text = 'Use A/D to turn left/right'
                elif tutorial_text == 'strafe':
                    if settings.MOUSE_TURNING:
                        tutorial_text = 'Use A/D to strafe left/right'
                    else:
                        tutorial_text = ''

                position = V2(item["x"], item["y"])
                entity = Entity()
                entity.attach(PhysicsComponent(position=position))
                visual = Visual(
                    kind="tutorial text",
                    z_sort = -20,
                    value=pyglet.text.Label(
                        tutorial_text,
                        align="center",
                        multiline=True,
                        font_size=36,
                        width=600,
                        anchor_x="center",
                        anchor_y="center",
                    )
                )
                entity.attach(GameVisualComponent(visuals=[visual]))

        flight_path = Entity()

        with open(os.path.join("maps", f"{map_name}_path.json"), "r") as f:
            map_path_data = f.read()
        map_path = json.loads(map_path_data)

        points = [V2(p["x"], p["y"]) for p in map_path]
        checkpoints = [
            {
                "center": points[i],
                "rotation": (
                    (points[i + 1] - points[i]).degrees - 90
                    if i == 0
                    else (points[i] - points[i - 1]).degrees - 90
                ),
            }
            for i, p in enumerate(map_path)
            if "checkpoint" in p
        ]

        for cp_order, checkpoint in enumerate(checkpoints):
            position = checkpoint["center"]
            rotation = checkpoint["rotation"]
            self.load_checkpoint(position, rotation, cp_order, map_entity.entity_id)

        points_p = []
        for p in points:
            points_p.append(p.x)
            points_p.append(p.y)

        fp_component = FlightPathComponent(path=points)

        infinite_magenta = cycle((255, 0, 255, 50))

        base_batch = pyglet.graphics.Batch()
        flare_batch = pyglet.graphics.Batch()

        for i, point in enumerate(points):
            if i % 2 == 0:
                continue
            v = points[i] - points[i - 1]
            a = V2.from_degrees_and_length(v.degrees + 90, 150) + point
            b = V2.from_degrees_and_length(v.degrees - 90, 150) + point

            # Create the base flare sprites (unlit flare)
            fp_component.flares.append(pyglet.sprite.Sprite(
                ASSETS["base_flare"],
                x=a.x, y=a.y, batch=base_batch
            ))

            fp_component.flares.append(pyglet.sprite.Sprite(
                ASSETS["base_flare"],
                x=b.x, y=b.y, batch=base_batch
            ))

            # Create the overlay/light flare sprites
            fp_component.flares.append(pyglet.sprite.Sprite(
                ASSETS["particle_flare"],
                x=a.x, y=a.y, batch=flare_batch,
                blend_src=pyglet.gl.GL_SRC_ALPHA,
                blend_dest=pyglet.gl.GL_ONE,
            ))

            fp_component.flares.append(pyglet.sprite.Sprite(
                ASSETS["particle_flare"],
                x=b.x, y=b.y, batch=flare_batch,
                blend_src=pyglet.gl.GL_SRC_ALPHA,
                blend_dest=pyglet.gl.GL_ONE,
            ))

        flare_bases_visual = Visual(kind="sprite batch", z_sort=-14, value=base_batch)
        flare_flares_visual = Visual(kind="sprite batch", z_sort=-13, value=flare_batch)

        flight_path.attach(fp_component)
        flight_path.attach(GameVisualComponent(visuals=[
            flare_bases_visual,
            flare_flares_visual,
        ]))

        map_.origin = points[0]

        ship_entity = get_ship_entity()
        ship_physics = ship_entity['physics']
        ship_physics.position = map_.origin
        ship_physics.velocity = V2(0, 0)
        System.dispatch(event="CenterCamera")

        return map_entity.entity_id
