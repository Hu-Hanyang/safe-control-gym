'''Template training/plotting/testing script.'''

import os
import shutil
from functools import partial

import munch
import yaml

from safe_control_gym.utils.configuration import ConfigFactory
from safe_control_gym.utils.plotting import plot_from_logs
from safe_control_gym.utils.registration import make
from safe_control_gym.utils.utils import mkdirs, set_device_from_config, set_seed_from_config


def train_game():
    '''Training template.
    '''
    # Create the configuration dictionary.
    fac = ConfigFactory()
    config = fac.merge()
    config.algo_config['training'] = True
    config.algo_config['max_ctrl_steps'] = config.task_config['episode_len_sec'] * config.task_config['ctrl_freq']
    total_steps = config.algo_config['max_env_steps']
    # For take in some attributes to the algorithm
    config.algo_config['render_height'] = config.task_config['render_height']
    config.algo_config['render_width'] = config.task_config['render_width']

    # shutil.rmtree(config.output_dir, ignore_errors=True)
    # Hanyang: create new envs
    output_dir = os.path.join(config.output_dir, "game", config.algo, f'seed_{config.seed}', f'{total_steps}steps')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir+'/')
    config.output_dir = output_dir
    print(f"The output directory is {config.output_dir}. \n")

    set_seed_from_config(config)
    set_device_from_config(config)

    # Define function to create task/env.
    env_func = partial(make,
                       config.task,
                       output_dir=config.output_dir,
                       **config.task_config
                       )
    print(f"==============The envs are ready.============== \n")
    

    # Create the controller/control_agent.
    ctrl = make(config.algo,
                env_func,
                checkpoint_path=os.path.join(config.output_dir, 'model_latest.pt'),
                output_dir=config.output_dir,
                use_gpu=config.use_gpu,
                seed=config.seed,
                **config.algo_config)
    ctrl.reset()
    print(f"==============The controller is ready.============== \n")

    # Training.
    print(f"==============Start training.============== \n")
    ctrl.learn()
    ctrl.close()
    print(f"==============Training done.============== \n")

    # Save the configuration.
    if config.task == 'cartpole' or config.task == 'cartpole_v0':
        env_func().close()
        with open(os.path.join(config.output_dir, 'config.yaml'), 'w', encoding='UTF-8') as file:
            config_assemble = munch.unmunchify(config)
            yaml.dump(config_assemble, file, default_flow_style=False)
    else:
        env_distb_type = env_func().distb_type
        env_distb_level = env_func().distb_level
        env_func().close()
        with open(os.path.join(config.output_dir, 'config.yaml'), 'w', encoding='UTF-8') as file:
            config_assemble = munch.unmunchify(config)
            config_assemble['env_distb_type'] = env_distb_type
            config_assemble['env_distb_level'] = env_distb_level
            yaml.dump(config_assemble, file, default_flow_style=False)
       

    make_plots(config)


def make_plots(config):
    '''Produces plots for logged stats during training.
    Usage
        * use with `--func plot` and `--restore {dir_path}` where `dir_path` is
            the experiment folder containing the logs.
        * save figures under `dir_path/plots/`.
    '''
    # Define source and target log locations.
    log_dir = os.path.join(config.output_dir, 'logs')
    plot_dir = os.path.join(config.output_dir, 'plots')
    mkdirs(plot_dir)
    plot_from_logs(log_dir, plot_dir, window=3)
    print('Plotting done.')


if __name__ == '__main__':
    train_game()