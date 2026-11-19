#!/usr/bin/env python3
"""Build an articulated MuJoCo fixture from the supplied fixture.obj."""

import argparse
import hashlib
import math
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from zipfile import ZipFile

SOURCE_SHA256 = "af1ce53c886f0b6871ced78f82d5e98986d1f73f8534a651f3985e48d8751d89"
TEMPLATE = Path(__file__).with_name("fixture.xml")
WORKPIECE_TEMPLATE = TEMPLATE.with_name("workpiece.xml")
BASE_PIVOT = (-0.165001, 0.010305, -0.0245)
CRANK_PIN = (-0.1537, 0.019488, -0.0154)
CARRIAGE_PIN = (0.036075, 0.010297, -0.0154)

# Indices are connected components of the supplied OBJ, ordered by union-find root.
# The source digest guards the component IDs and the measured pin locations.
MOVING_PARTS = {
    "handle": ({19, 29}, BASE_PIVOT),
    "rod": ({18}, CRANK_PIN),
    "carriage": (set(range(16)) | {24}, CARRIAGE_PIN),
}


def split_mesh(source, destination):
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("fixture.obj differs from the mesh used to identify the moving parts.")

    vertices, faces = [], []
    with source.open() as obj:
        for line in obj:
            if line.startswith("v "):
                vertices.append(tuple(map(float, line.split()[1:4])))
            elif line.startswith("f "):
                faces.append(tuple(int(token.split("/")[0]) - 1 for token in line.split()[1:]))

    parent = list(range(len(vertices)))

    def find(index):
        while index != parent[index]:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for a, b, c in faces:
        root = find(a)
        parent[find(b)] = root
        parent[find(c)] = root

    roots = [find(index) for index in range(len(vertices))]
    component_ids = {root: i for i, root in enumerate(sorted(set(roots)))}
    part_names = {
        component: name for name, (components, _) in MOVING_PARTS.items()
        for component in components
    }
    parts = {"base": [], **{name: [] for name in MOVING_PARTS}}
    for face in faces:
        part = part_names.get(component_ids[roots[face[0]]], "base")
        parts[part].append(face)

    destination.mkdir(parents=True, exist_ok=True)
    for name, part_faces in parts.items():
        origin = MOVING_PARTS[name][1] if name in MOVING_PARTS else (0, 0, 0)
        indices = dict.fromkeys(i for face in part_faces for i in face)
        with (destination / f"{name}.obj").open("w") as out:
            out.write(f"# {name}: geometry from fixture.obj, meters\n")
            for number, index in enumerate(indices, start=1):
                indices[index] = number
                relative = [value - offset for value, offset in zip(vertices[index], origin)]
                out.write("v " + " ".join(f"{value:.8f}" for value in relative) + "\n")
            for face in part_faces:
                out.write("f " + " ".join(str(indices[index]) for index in face) + "\n")


def merge_fixture(scene, fixture):
    for name in ("asset", "worldbody", "equality"):
        target = scene.find(name)
        if target is None:
            target = ET.SubElement(scene, name)
        target.extend(fixture.find(name))

    # Preserve initial coordinates for the new joints in existing keyframes.
    position, velocity = " 0 0 0", " 0 0 0"
    part = fixture.find(".//body[@name='fixture_workpiece']")
    if part is not None:
        half_angle = float(part.get("axisangle").split()[-1]) / 2
        position += f" {part.get('pos')} {math.cos(half_angle)} 0 0 {math.sin(half_angle)}"
        velocity += " 0 0 0 0 0 0"
    for key in scene.findall("./keyframe/key"):
        if "qpos" in key.attrib:
            key.set("qpos", key.get("qpos") + position)
        if "qvel" in key.attrib:
            key.set("qvel", key.get("qvel") + velocity)


def add_workpiece(fixture, source, destination, position, yaw):
    part = ET.parse(WORKPIECE_TEMPLATE).getroot()
    fixture.find("asset").extend(part.find("asset"))
    body = part.find("./worldbody/body")
    x, y, z = map(float, body.get("pos").split())
    cos, sin = math.cos(yaw), math.sin(yaw)
    xyz = (position[0] + cos*x - sin*y, position[1] + sin*x + cos*y, position[2] + z)
    body.set("pos", " ".join(map(str, xyz)))
    body.set("axisangle", f"0 0 1 {yaw - math.pi/2}")

    # Four boxes around each modeled ear hole let the pin pass through the opening.
    for center in (-.059847, .075153):
        for x, y, half_x, half_y in [
            (center, -.09164, .012, .00375),
            (center, -.10564, .012, .00375),
            (center - .008, -.09864, .004, .00325),
            (center + .008, -.09864, .004, .00325),
        ]:
            ET.SubElement(body, "geom", type="box", group="3", pos=f"{x} {y} -.054905",
                          size=f"{half_x} {half_y} .0025", contype="1", conaffinity="9",
                          rgba=".76 .53 .24 .3")

    world = fixture.find("worldbody")
    world.append(body)
    base = world.find("./body[@name='fixture_base']")
    for y in (-.08255, .08345):
        # The original file omits the front ear. Support the front shell corners.
        ET.SubElement(base, "geom", type="box", group="3", pos=f".041125 {y} -.016375",
                      size=".009 .008 .008", contype="2", conaffinity="1", rgba="0 0 0 0")
    for y in (-.0747, .0603):
        ET.SubElement(base, "geom", type="cylinder", group="3", pos=f"-.1315 {y} -.005375",
                      size=".0032 .003", contype="2", conaffinity="1", rgba="0 0 0 0")
    shutil.copyfile(source, destination / "fixture_assets" / "workpiece.obj")


def write_xml(root, path):
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Original fixture.obj")
    parser.add_argument("output", type=Path, help="Directory for model.xml and meshes")
    parser.add_argument("--workpiece", type=Path, help="Add the original workpiece.obj in its seated pose")
    parser.add_argument("--robot-scene", type=Path, help="Existing Lycus MJZ archive")
    parser.add_argument("--position", nargs=3, type=float, default=None, metavar=("X", "Y", "Z"),
                        help="Fixture origin in world coordinates, meters")
    parser.add_argument("--yaw", type=float, default=0.0, help="Rotation around vertical, radians")
    args = parser.parse_args()

    if args.robot_scene and args.position is None:
        parser.error("--robot-scene requires --position")
    split_mesh(args.source, args.output / "fixture_assets")
    fixture = ET.parse(TEMPLATE).getroot()
    fixture_base = fixture.find("./worldbody/body")
    if args.position is not None:
        fixture_base.set("pos", " ".join(map(str, args.position)))
    fixture_base.set("axisangle", f"0 0 1 {args.yaw}")
    if args.workpiece:
        add_workpiece(fixture, args.workpiece, args.output, args.position or (0, 0, 0), args.yaw)

    model = fixture
    if args.robot_scene:
        with ZipFile(args.robot_scene) as archive:
            model = ET.fromstring(archive.read("model.xml"))
            compiler = model.find("compiler")
            if compiler is None or compiler.get("angle") != "radian":
                parser.error("the robot scene must use angle=\"radian\"")
            if model.find(".//body[@name='fixture_base']") is not None:
                parser.error("the robot scene already contains fixture_base")
            archive.extractall(args.output, members=[
                name for name in archive.namelist() if name.startswith("assets/")
            ])
        merge_fixture(model, fixture)
    write_xml(model, args.output / "model.xml")
    print(args.output.resolve() / "model.xml")


if __name__ == "__main__":
    main()
