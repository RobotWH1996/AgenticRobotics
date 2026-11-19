#!/usr/bin/env python3
"""Assemble a two-table Lycus scene with one seated, clamped workpiece."""

import argparse
import copy
import math
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from build_fixture import BASE_PIVOT, CARRIAGE_PIN, CRANK_PIN, TEMPLATE, add_workpiece, split_mesh, write_xml


FLOOR = -.313
TCP_POS = (-.011975, 0., .3365)
TABLE_HALF = (.25, .34)


def vec(values):
    return " ".join(f"{value:.10g}" for value in values)


def fixture_pose(base, position, yaw):
    base.set("pos", vec(position))
    base.set("axisangle", vec((0, 0, 1, yaw)))


def close_fixture(base):
    handle = base.find("./body[@name='fixture_handle']")
    rod = handle.find("body")
    slide = base.find("./body[@name='fixture_carriage']")
    angle = float(handle.find("joint").get("range").split()[1])
    cosine, sine = math.cos(angle), math.sin(angle)
    a, b = (CRANK_PIN[i] - BASE_PIVOT[i] for i in range(2))
    pin_x = BASE_PIVOT[0] + cosine*a - sine*b
    pin_y = BASE_PIVOT[1] + sine*a + cosine*b
    dx, dy = (CARRIAGE_PIN[i] - CRANK_PIN[i] for i in range(2))
    y_to_slide = CARRIAGE_PIN[1] - pin_y
    x_to_slide = math.sqrt(dx*dx + dy*dy - y_to_slide*y_to_slide)
    rod_angle = math.atan2(y_to_slide, x_to_slide) - math.atan2(dy, dx) - angle
    travel = pin_x + x_to_slide - CARRIAGE_PIN[0]

    # Set the actual MJCF reference pose, so normal MjData construction
    # starts closed and the hinge limits remain in the open-state convention.
    for body, value in ((handle, angle), (rod, rod_angle)):
        body.set("axisangle", vec((0, 0, 1, value)))
        body.find("joint").set("ref", str(value))
    slide.set("pos", vec((CARRIAGE_PIN[0] + travel, *CARRIAGE_PIN[1:])))
    slide.find("joint").set("ref", str(travel))


def namespace_fixture(base, closure, prefix):
    for item in (*base.iter(), closure):
        for key in ("name", "site1", "site2"):
            if key in item.attrib:
                item.set(key, f"{prefix}_{item.get(key)}")


def add_table(world, name, x, top):
    table = ET.SubElement(world, "body", name=name, pos=vec((x, 0, top)))
    ET.SubElement(table, "geom", name=f"{name}_top", type="box", pos="0 0 -.025",
                  size=vec((*TABLE_HALF, .025)), rgba=".26 .34 .41 1",
                  contype="2", conaffinity="9")
    leg_height = (top - .05 - FLOOR) / 2
    for x_sign in (-1, 1):
        for y_sign in (-1, 1):
            ET.SubElement(table, "geom", type="box", pos=vec((.20*x_sign, .28*y_sign, -.05-leg_height)),
                          size=vec((.023, .023, leg_height)), rgba=".38 .44 .50 1",
                          contype="2", conaffinity="9")


def add_camera(world, name, position, target, fovy):
    z = tuple(a - b for a, b in zip(position, target))
    x = (-z[1], z[0], 0)
    y = (z[1]*x[2]-z[2]*x[1], z[2]*x[0]-z[0]*x[2], z[0]*x[1]-z[1]*x[0])
    ET.SubElement(world, "camera", name=name, pos=vec(position), xyaxes=vec((*x, *y)),
                  fovy=str(fovy))


def configure_robot(world):
    for geom in world.iter("geom"):
        # Robot collision hulls overlap in the source model. Preserve their
        # contacts with the environment using a separate collision layer.
        if geom.get("contype") != "0":
            geom.set("contype", "8")
            geom.set("conaffinity", "2")
            geom.set("group", "3")
    for side in ("L", "R"):
        wrist = world.find(f".//body[@name='AR5-5_08{side}-W4C1C5-ZY2_link7']")
        if wrist is None:
            raise ValueError("Expected Lycus left and right wrist bodies.")
        ET.SubElement(wrist, "site", name=f"gap_{side}_tcp", pos=vec(TCP_POS),
                      quat="0.5 0.5 0.5 0.5", size=".003", rgba="0 0 0 0")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robot-scene", type=Path, required=True, help="Lycus MJZ archive")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--workpiece", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--table-top", type=float, default=.91, help="Table top Z in Lycus base frame")
    parser.add_argument("--front-x", type=float, default=.74)
    parser.add_argument("--rear-x", type=float, default=-.84)
    args = parser.parse_args()
    if args.front_x <= 0 or args.rear_x >= 0 or args.table_top <= FLOOR + .05:
        parser.error("front-x must be positive, rear-x negative and the table must be above the floor")

    split_mesh(args.fixture, args.output / "fixture_assets")
    with ZipFile(args.robot_scene) as archive:
        scene = ET.fromstring(archive.read("model.xml"))
        archive.extractall(args.output, [name for name in archive.namelist() if name.startswith("assets/")])
    if scene.find("compiler").get("angle") != "radian":
        raise ValueError("Expected a Lycus MJZ archive using radians.")
    if scene.find("keyframe") is not None:
        raise ValueError("Use the baseline Lycus archive without keyframes.")

    scene.set("model", "lycus_two_fixture_tables")
    option = scene.find("option")
    if option is None:
        option = ET.SubElement(scene, "option")
    option.set("timestep", ".001")
    option.set("integrator", "implicitfast")
    world = scene.find("worldbody")
    configure_robot(world)
    ET.SubElement(world, "geom", name="floor", type="plane", pos=vec((0, 0, FLOOR)),
                  size="3 3 .01", rgba=".71 .74 .79 1", contype="2", conaffinity="1")
    ET.SubElement(world, "light", directional="true", pos="1 -1 3", dir="-.3 .3 -1",
                  diffuse=".52 .52 .52", ambient=".23 .23 .23")
    ET.SubElement(world, "light", directional="true", pos="-1 1 3", dir=".3 -.3 -1",
                  diffuse=".23 .23 .23", castshadow="false")

    assembly = ET.parse(TEMPLATE).getroot()
    front = assembly.find("./worldbody/body")
    fixture_z = args.table_top + .034375
    front_position = args.front_x, 0, fixture_z
    fixture_pose(front, front_position, 0.)
    add_workpiece(assembly, args.workpiece, args.output, front_position, 0.)
    rear = copy.deepcopy(front)
    fixture_pose(rear, (args.rear_x, 0, fixture_z), math.pi)
    close_fixture(front)

    linkage = assembly.find("./equality/connect")
    rear_linkage = copy.deepcopy(linkage)
    namespace_fixture(front, linkage, "front")
    namespace_fixture(rear, rear_linkage, "rear")
    scene.find("asset").extend(assembly.find("asset"))
    equality = scene.find("equality")
    if equality is None:
        equality = ET.SubElement(scene, "equality")
    equality.extend((linkage, rear_linkage))

    add_table(world, "front_table", args.front_x, args.table_top)
    add_table(world, "rear_table", args.rear_x, args.table_top)
    world.extend((front, rear, assembly.find("./worldbody/body[@name='fixture_workpiece']")))
    add_camera(world, "agentview", (1.9, -3.25, 2.45), (0, 0, .73), 42)
    add_camera(world, "front_fixture_view",
               (args.front_x + .62, -.62, args.table_top + .83), front_position, 44)
    add_camera(world, "rear_fixture_view",
               (args.rear_x - .62, -.62, args.table_top + .83), (args.rear_x, 0, fixture_z), 44)
    write_xml(scene, args.output / "model.xml")
    print(args.output.resolve() / "model.xml")


if __name__ == "__main__":
    main()
