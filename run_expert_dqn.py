import matplotlib.pyplot as plt
import pandas as pd
import os
import logging

import tensorflow as tf
import datetime
import gym
import energym
import time
import argparse
import pickle
import pandas as pd

import agents.dqn as dqn
from agents.dqn_utils import *

import warnings
warnings.filterwarnings("ignore", message="numpy.dtype size changed")
warnings.filterwarnings("ignore", message="numpy.ufunc size changed")


def model(input, num_actions, scope, reuse=False):
    with tf.variable_scope(scope, reuse=reuse):
        out = input
        with tf.variable_scope("action_value"):
            out = tf.contrib.layers.fully_connected(out, num_outputs=32,         activation_fn=tf.nn.relu)
            out = tf.contrib.layers.fully_connected(out, num_outputs=num_actions, activation_fn=None)
        return out


def create_controller(env,
          session,
          num_timesteps,
          save_path,
          rew_file,
          with_expert):

    # This is just a rough estimate
    num_iterations = float(num_timesteps) / 4.0

    lr_multiplier = 1.0
    lr_schedule = PiecewiseSchedule([
                                         (0,                   1e-4 * lr_multiplier),
                                         (num_iterations / 10, 1e-4 * lr_multiplier),
                                         (num_iterations / 2,  5e-5 * lr_multiplier),
                                    ],
                                    outside_value=5e-5 * lr_multiplier)
    optimizer = dqn.OptimizerSpec(
        constructor=tf.train.AdamOptimizer,
        kwargs=dict(epsilon=1e-4),
        lr_schedule=lr_schedule
    )

    def stopping_criterion(env, t):
        # notice that here t is the number of steps of the wrapped env,
        # which is different from the number of steps in the underlying env
        return t > num_timesteps

    exploration_schedule = PiecewiseSchedule(
        [
            (0, 1.0),
            (5e4, 0.01),
            (num_iterations / 2, 0.01),
        ], outside_value=0.01
    )

    controller = dqn.QLearner(
        env=env,
        q_func=model,
        optimizer_spec=optimizer,
        session=session,
        exploration=exploration_schedule,
        stopping_criterion=stopping_criterion,
        rew_file=rew_file,
        replay_buffer_size=1000000,
        batch_size=32,
        gamma=0.95,
        learning_starts=500,
        learning_freq=4,
        frame_history_len=4,
        target_update_freq=1000,
        grad_norm_clipping=10,
        double_q=True,
        save_path=save_path,
        with_expert=with_expert
    )

    return controller


def test_model(controller):
    return controller.test_model()


def get_available_gpus():
    from tensorflow.python.client import device_lib
    local_device_protos = device_lib.list_local_devices()
    return [x.physical_device_desc for x in local_device_protos if x.device_type == 'GPU']


def get_session():
    tf.reset_default_graph()
    tf_config = tf.ConfigProto(
        inter_op_parallelism_threads=1,
        intra_op_parallelism_threads=1)
    session = tf.Session(config=tf_config)
    print("AVAILABLE GPUS: ", get_available_gpus())
    return session


def main():
    # ************ ARGPARSE ************
    parser = argparse.ArgumentParser()
    parser.add_argument('--rew_file', '-rf', type=str, default=None,
                        help='Path for the rewards file (optional).')
    parser.add_argument("--test", "-t", action="store_true")
    args = parser.parse_args()

    # ************ MAIN ************
    start_time = datetime.datetime.now()
    start_time = [start_time.day,start_time.hour,
                  start_time.minute, start_time.second]

    env = gym.make('energy_market_battery-v1')

    # initialize
    session = get_session()

    controller = create_controller(
    	env, 
    	session, 
    	num_timesteps=1e8, 
    	save_path='/tmp/model_2.ckpt', 
    	rew_file=args.rew_file, 
    	with_expert=True
    	)

    # train controller
    if not args.test:
        try:
            while not controller.stopping_criterion_met():
                    controller.step_env()
                    controller.update_model()
                    controller.log_progress()
        except KeyboardInterrupt:
            print("KeyboardInterrupt error caught")
    else:
        controller.saver.restore(controller.session, '/tmp/model_2.ckpt')
        # FixMe: Ugly
        controller.env._energy_market._gen_df = pd.read_pickle("data/gen_caiso.pkl")
        controller.env._energy_market._dem_df = pd.read_pickle("data/dem_caiso.pkl")

    env.close()

    # test controller
    save_dict = test_model(controller)

    # save result
    with open('results/{}_{}_{}_{}.pkl'.format(*start_time), 'wb') as pickle_file:
        pickle.dump(save_dict, pickle_file, protocol=pickle.HIGHEST_PROTOCOL)



if __name__ == "__main__":
    main()