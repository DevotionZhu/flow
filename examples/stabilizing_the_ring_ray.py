"""
Script used to train test platooning on a single lane.

RL vehicles are bunched together. The emergent behavior we are hoping to witness
is that rl-vehicles group together in other to allow non rl-vehicles a larger headway,
and thus larger equilibrium speeds.

One concern is whether rl-vehicles will start tail-gating human vehicles.
"""

import logging

import gym
import numpy as np

import ray
import ray.rllib.ppo as ppo
from ray.tune.registry import get_registry, register_env as register_rllib_env
from ray.rllib.models import ModelCatalog

from flow.core.util import register_env
from flow.utils.tuple_preprocessor import TuplePreprocessor

from flow.core.params import SumoParams, EnvParams, InitialConfig, NetParams
from flow.scenarios.loop.gen import CircleGenerator
from flow.scenarios.loop.loop_scenario import LoopScenario
from flow.controllers.rlcontroller import RLController
from flow.controllers.car_following_models import IDMController
from flow.controllers.routing_controllers import ContinuousRouter
from flow.core.vehicles import Vehicles


def make_create_env(flow_env_name, version):
    env_name = flow_env_name+'-v%s' % version

    def create_env():
        # Experiment prefix
        exp_tag = "22-car-stabilizing-the-ring-local-robust-0-std"

        import flow.envs as flow_envs
        logging.basicConfig(level=logging.INFO)

        sumo_params = SumoParams(sim_step=0.1, sumo_binary="sumo")

        vehicles = Vehicles()
        vehicles.add_vehicles(veh_id="rl",
                              acceleration_controller=(RLController, {}),
                              routing_controller=(ContinuousRouter, {}),
                              num_vehicles=1)
        vehicles.add_vehicles(veh_id="idm",
                              acceleration_controller=(IDMController, {}),
                              routing_controller=(ContinuousRouter, {}),
                              num_vehicles=21)

        additional_env_params = {"target_velocity": 8, "max-deacc": -1,
                                 "max-acc": 1, "num_steps": 3600,
                                 "scenario_type": LoopScenario}
        env_params = EnvParams(additional_params=additional_env_params)

        additional_net_params = {"length": 260, "lanes": 1, "speed_limit": 30,
                                 "resolution": 40}
        net_params = NetParams(additional_params=additional_net_params)

        initial_config = InitialConfig(spacing="uniform", bunching=50)

        scenario = LoopScenario(exp_tag, CircleGenerator, vehicles, net_params,
                                initial_config=initial_config)

        pass_params = (flow_env_name, sumo_params, vehicles, env_params,
                       net_params, initial_config, scenario, version)

        register_env(*pass_params)
        env = gym.envs.make(env_name)

        env.observation_space.shape = (
            int(np.sum([c.shape for c in env.observation_space.spaces])),)

        ModelCatalog.register_preprocessor(env_name, TuplePreprocessor)

        return env
    return create_env, env_name

if __name__ == "__main__":
    config = ppo.DEFAULT_CONFIG.copy()
    horizon = 3600
    # ray.init(num_cpus=16)
    # ray.init(redis_address="172.31.92.24:6379", redirect_output=True)
    num_cpus=4
    ray.init(num_cpus=num_cpus, redirect_output=True)
    config["num_workers"] = max(100, num_cpus)
    config["timesteps_per_batch"] = horizon * 4
    config["num_sgd_iter"] = 10
    config["model"].update({"fcnet_hiddens": [16, 16]})
    config["gamma"] = 0.999
    config["horizon"] = horizon

    flow_env_name = "WaveAttenuationPOEnv"
    create_env, env_name = make_create_env(flow_env_name, 0)

    # Register as rllib env
    register_rllib_env(env_name, create_env)

    alg = ppo.PPOAgent(env=env_name, registry=get_registry(), config=config)
    for i in range(2):
        alg.train()
        if i % 20 == 0:
            print("XXXX checkpoint path is", alg.save())
