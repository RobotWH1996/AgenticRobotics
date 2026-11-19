"""Lycus two-table fixture scene backed by native MuJoCo."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import math
from pathlib import Path
from threading import Lock
import time
from types import SimpleNamespace

import mujoco
import numpy as np

from gap.connector.robot_io_env import ArmLayout, RobotIOEnv
from gap.connector.world_adapter import LiberoWorldAdapter
from gap.envs.registry import EnvConfig
from gap.robot_io import CameraSample, RobotSample, validate_command
from gap.runtime.verify import Robot

ARM_STANDBY = (0., .45, 0., 1.45, 0., 0., 0.)
CAMERAS = ("agentview", "front_fixture_view", "rear_fixture_view")
OBJECTS = {
    "front_table": "front_table",
    "rear_table": "rear_table",
    "front_fixture": "front_fixture_base",
    "rear_fixture": "rear_fixture_base",
    "workpiece": "fixture_workpiece",
}
CONTROL_FREQ = 20
DEFAULT_SCENE = (
    Path(__file__).resolve().parents[2] / "outputs" / "scenes" / "lycus_fixture" / "model.xml"
)


def arm_layout(side):
    label = "left" if side == "L" else "right"
    return ArmLayout(
        tuple(f"AR5-5_08{side}-W4C1C5-ZY2_joint_{i}" for i in range(1, 8)),
        (f"{label}_gripper", f"{label}_gripper_mimic"),
        lambda q: float(np.clip(1 + (q[0] - q[1]) / .084, 0, 1)),
        lambda fraction: np.array([-.042, .042]) * (1 - fraction),
    )


class LycusSceneIO:
    """Advance MuJoCo under position targets supplied by GaP's RobotIO adapter."""

    control_period_s = 1 / CONTROL_FREQ

    def __init__(self, scene, cameras):
        self.model = mujoco.MjModel.from_xml_path(str(scene))
        self.data = mujoco.MjData(self.model)
        self.cameras = cameras
        self.renderer = None
        self.render_worker = ThreadPoolExecutor(max_workers=1) if cameras else None
        self.lock = Lock()
        self.scene_options = mujoco.MjvOption()
        self.scene_options.geomgroup[3] = 0
        self.sequence = 0
        self.camera_sequence = -1
        self.frames = {}
        self.video_enabled = False
        self.video_frames = []
        count = self.model.joint("front_fixture_handle_hinge").id
        self.joint_names = tuple(self.model.joint(i).name for i in range(count))
        self.qpos_indices = self.model.jnt_qposadr[:count]
        self.dof_indices = self.model.jnt_dofadr[:count]
        self.lower = np.where(self.model.jnt_limited[:count], self.model.jnt_range[:count, 0], -np.inf)
        self.upper = np.where(self.model.jnt_limited[:count], self.model.jnt_range[:count, 1], np.inf)
        effort_limits = self.model.jnt_actfrcrange[:count]
        self.effort = np.where(effort_limits[:, 1] > 0, effort_limits[:, 1], 100)
        self.acceleration = np.zeros(self.model.nv)
        self.effort_work = np.zeros(self.model.nv)
        self.initial = self.model.qpos0.copy()
        for side in ("L", "R"):
            for name, value in zip(arm_layout(side).joint_names, ARM_STANDBY, strict=True):
                self.initial[self.model.joint(name).qposadr.item()] = value
        self.initial[self.model.joint("Head_joint").qposadr.item()] = .35
        self.reset()

    def reset(self):
        with self.lock:
            mujoco.mj_resetData(self.model, self.data)
            self.data.qpos[:] = self.initial
            self.camera_sequence = -1
            mujoco.mj_forward(self.model, self.data)

    def sample(self):
        return RobotSample(
            sequence=self.sequence,
            timestamp_s=float(self.data.time),
            joint_positions=self.data.qpos[self.qpos_indices],
            joint_velocities=self.data.qvel[self.dof_indices],
            cameras=self.frames,
        )

    def observe(self):
        with self.lock:
            if self.render_worker is not None and self.camera_sequence != self.sequence:
                self.frames = self.render_worker.submit(self.capture_cameras).result()
                self.camera_sequence = self.sequence
            return self.sample()

    def capture_cameras(self):
        # EGL binds its context to one thread. GaP can call observe() both
        # from the workflow thread and from its observation stream.
        return {name: self.render_camera(name) for name in self.cameras}

    def exchange(self, command):
        validate_command(command, len(self.joint_names))
        if command.kp is not None or command.kd is not None:
            raise ValueError("The Lycus scene uses fixed joint tracking gains.")
        with self.lock:
            target = np.clip(command.positions, self.lower, self.upper)
            qpos, dofs = self.qpos_indices, self.dof_indices
            for _ in range(round(self.control_period_s / self.model.opt.timestep)):
                self.acceleration[dofs] = 600*(target - self.data.qpos[qpos]) - 50*self.data.qvel[dofs]
                mujoco.mj_mulM(self.model, self.data, self.effort_work, self.acceleration)
                effort = self.effort_work[dofs] + self.data.qfrc_bias[dofs] - self.data.qfrc_passive[dofs]
                self.data.qfrc_applied[dofs] = np.clip(effort, -self.effort, self.effort)
                mujoco.mj_step(self.model, self.data)
            self.sequence += 1
            if self.video_enabled:
                self.video_frames.append(self.render_worker.submit(self.render_rgb, "agentview").result())
            return self.sample()

    def render_rgb(self, name):
        if self.renderer is None:
            self.renderer = mujoco.Renderer(self.model, height=480, width=640)
        renderer = self.renderer
        renderer.update_scene(self.data, camera=name, scene_option=self.scene_options)
        return renderer.render()

    def render_camera(self, name):
        rgb = self.render_rgb(name)
        renderer = self.renderer
        renderer.enable_depth_rendering()
        try:
            depth = renderer.render()
        finally:
            renderer.disable_depth_rendering()
        height, width = depth.shape
        focal = height / (2 * math.tan(math.radians(self.model.camera(name).fovy.item()) / 2))
        intrinsics = np.array([[focal, 0, width/2], [0, focal, height/2], [0, 0, 1]])
        pose = np.eye(4)
        camera = self.data.camera(name)
        pose[:3, 3] = camera.xpos
        # MuJoCo +Y is image-up and -Z looks forward. GaP uses optical axes.
        pose[:3, :3] = camera.xmat.reshape(3, 3) @ np.diag([1, -1, -1])
        return CameraSample(rgb, depth, intrinsics, pose, float(self.data.time))

    def close(self):
        if self.render_worker is not None:
            if self.renderer is not None:
                self.render_worker.submit(self.renderer.close).result()
                self.renderer = None
            self.render_worker.shutdown()
            self.render_worker = None


class SceneEnv(RobotIOEnv):
    def __init__(self, scene, cameras):
        io = LycusSceneIO(scene, cameras)
        arms = tuple(arm_layout(side) for side in ("L", "R"))
        fk_data = mujoco.MjData(io.model)
        fk_data.qpos[:] = io.initial
        qpos = tuple([io.model.joint(name).qposadr.item() for name in arm.joint_names] for arm in arms)

        fk_lock = Lock()

        def fk(arm_id, joints):
            with fk_lock:
                fk_data.qpos[qpos[arm_id]] = joints
                mujoco.mj_kinematics(io.model, fk_data)
                site = fk_data.site(("gap_L_tcp", "gap_R_tcp")[arm_id])
                transform = np.eye(4)
                transform[:3, :3] = site.xmat.reshape(3, 3)
                transform[:3, 3] = site.xpos
                return transform

        super().__init__(io, arms, fk)
        self.sim = SimpleNamespace(model=io.model, data=io.data)
        self.obj_body_id = {name: io.model.body(body).id for name, body in OBJECTS.items()}
        self.world_adapter = SceneWorldAdapter(self)
        self.ik_backend = JointControlOnly()
        self.front_hinge = io.model.joint("front_fixture_handle_hinge").id
        self.rear_hinge = io.model.joint("rear_fixture_handle_hinge").id
        dock = io.model.geom("fixture_workpiece_dock").id
        self.dock_pairs = {
            frozenset((io.model.geom(i).id, dock))
            for i in range(io.model.ngeom)
            if io.model.geom(i).name.startswith("front_fixture_press_")
        }

    def reset(self, *, seed=None):
        self.io.reset()
        self._sample = None
        self._target = None
        self._sim_step_count = 0
        return self.get_observation(), {}

    def get_observation(self):
        obs = super().get_observation()
        data = self.sim.data
        obs["cube_poses"] = {
            name: np.r_[data.xpos[body], data.xquat[body]]
            for name, body in self.obj_body_id.items()
        }
        return obs

    def task_completed(self):
        """Task 0 verifies that the initial clamped scene is ready."""
        model, data = self.sim.model, self.sim.data
        front = data.qpos[model.jnt_qposadr[self.front_hinge]]
        rear = data.qpos[model.jnt_qposadr[self.rear_hinge]]
        if abs(front - model.jnt_range[self.front_hinge, 1]) > .02 or abs(rear) > .02:
            return False
        force = np.zeros(6)
        for i, contact in enumerate(data.contact):
            if frozenset(contact.geom) in self.dock_pairs:
                mujoco.mj_contactForce(model, data, i, force)
                if force[0] > .05:
                    return True
        return False

    def compute_reward(self):
        return float(self.task_completed())

    def enable_video_capture(self, enabled, *, clear=True):
        with self.io.lock:
            if enabled and self.io.render_worker is None:
                self.io.render_worker = ThreadPoolExecutor(max_workers=1)
            if clear:
                self.io.video_frames.clear()
            self.io.video_enabled = enabled

    def get_video_frames(self, *, clear=False):
        with self.io.lock:
            frames = self.io.video_frames.copy()
            if clear:
                self.io.video_frames.clear()
            return frames

    def close(self):
        self.io.close()


class MuJoCoModelView:
    """Supply the name lookup methods used by GaP's robosuite world adapter."""

    def __init__(self, model):
        self.model = model

    def __getattr__(self, name):
        return getattr(self.model, name)

    def body_name2id(self, name):
        return self.model.body(name).id

    def body_id2name(self, index):
        return self.model.body(index).name


class MuJoCoDataView:
    def __init__(self, data):
        self.data = data

    def __getattr__(self, name):
        return getattr(self.data, name)

    @property
    def body_xpos(self):
        return self.data.xpos

    @property
    def body_xquat(self):
        return self.data.xquat


class SceneWorldAdapter(LiberoWorldAdapter):
    def __init__(self, env):
        self.scene_env = env
        view = SimpleNamespace(
            sim=SimpleNamespace(model=MuJoCoModelView(env.sim.model),
                                data=MuJoCoDataView(env.sim.data)),
            obj_body_id=env.obj_body_id,
            get_current_time_s=lambda: env.sim.data.time,
        )
        super().__init__(view, robot_link_prefixes=("AR5-", "left_gripper", "right_gripper"))

    def _robot_view(self, model, data, **_kwargs):
        # GaP's world snapshot exposes one Robot. Use arm 0 (Lycus left).
        arm = self.scene_env.arms[0]
        native = self.scene_env.sim.data
        joints = np.array([native.joint(name).qpos.item() for name in arm.joint_names])
        pose = self.scene_env.fk(0, joints)
        quat = np.zeros(4)
        mujoco.mju_mat2Quat(quat, pose[:3, :3].ravel())
        fingers = np.array([native.joint(name).qpos.item() for name in arm.gripper_joint_names])
        return Robot("robot", joints, arm.joint_names, pose[:3, 3], quat,
                     arm.gripper_fraction(fingers))


class JointControlOnly:
    """Require a Lycus-specific planner before running Cartesian graph nodes."""

    def solve_ik(self, *args, **kwargs):
        raise RuntimeError("Attach a Lycus IK backend for Cartesian graph nodes.")

    def plan_linear(self, *args, **kwargs):
        raise RuntimeError("Attach a Lycus motion planner for Cartesian graph nodes.")


def make_env(
    suite_name,
    task_id,
    *,
    camera_names=None,
    enable_render=False,
    scene_path=None,
    ik=None,
):
    """Factory for the registered Lycus scene."""
    if suite_name != "lycus_fixture" or task_id != 0:
        raise ValueError("The installed Lycus fixture scene uses lycus_fixture/0.")
    scene = Path(scene_path or DEFAULT_SCENE).expanduser().resolve()
    if not scene.is_file():
        raise FileNotFoundError(f"Lycus scene XML missing: {scene}")
    # Cameras are part of GaP observations even if video recording is disabled.
    cameras = CAMERAS if camera_names is None else tuple(camera_names)
    env = SceneEnv(scene, cameras)
    if ik is not None:
        env.ik_backend = ik
    config = EnvConfig(num_arms=2, home_joints=ARM_STANDBY, tcp_offset=(0., 0., 0.),
                       default_cameras=CAMERAS, control_freq=CONTROL_FREQ)
    return env, config


def show_scene(connector):
    from mujoco.viewer import launch_passive

    env = connector.env
    with launch_passive(env.sim.model, env.sim.data) as viewer:
        with viewer.lock():
            viewer.opt.geomgroup[3] = 0
            viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
            viewer.cam.fixedcamid = env.sim.model.camera("agentview").id
        while viewer.is_running():
            start = time.monotonic()
            with viewer.lock():
                env._step_once()
            viewer.sync()
            time.sleep(max(0., env.io.control_period_s - (time.monotonic() - start)))


def main():
    from gap.connector import sim

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewer", action="store_true", help="Open the MuJoCo viewer")
    args = parser.parse_args()
    with sim("lycus_fixture", task=0, cameras=[]) as connector:
        if args.viewer:
            show_scene(connector)
        else:
            connector.reset()
            for _ in range(20):
                connector.step_once()
            print("GaP scene objects:", ", ".join(connector.get_state()["objects"]))
            if not connector.check_success()[0]:
                raise RuntimeError("The front workpiece did not settle in its clamp.")


if __name__ == "__main__":
    main()
