from safe_control_gym.envs.gym_pybullet_drones.quadrotor import Quadrotor
from safe_control_gym.envs.gym_pybullet_drones.quadrotor_distb import QuadrotorDistb, QuadrotorFixedDistb, QuadrotorBoltzDistb, QuadrotorNullDistb, QuadrotorRandomDistb
from safe_control_gym.envs.gym_pybullet_drones.quadrotor_adversary import QuadrotorAdversary
import numpy as np
import imageio, os
import torch
from safe_control_gym.utils.registration import make
from safe_control_gym.controllers.rarl.rarl import RARL
from safe_control_gym.utils.configuration import ConfigFactoryTestAdversary



# Function to create GIF
def create_gif(image_list, filename, duration=0.1):
    images = []
    for img in image_list:
        images.append(img.astype(np.uint8))  # Convert to uint8 for imageio
    imageio.mimsave(f'{filename}', images, duration=duration)


# # --trained_task quadrotor_null --algo rarl --task quadrotor_randomhj  --seed 42
# fac = ConfigFactoryTestAdversary()
# config = fac.merge()
# config.algo_config['training'] = False
# config.output_dir = 'test_results/quadrotor_adversary'
# total_steps = config.algo_config['max_env_steps']
# # print(f"The config is {config}")
# trained_model = 'training_results/quadrotor_null/rarl/seed_42/10000000steps/model_latest.pt'
# env_func = QuadrotorNullDistb
# rarl = make(config.algo,
#             env_func,
#             checkpoint_path=os.path.join(config.output_dir, 'model_latest.pt'),
#             output_dir=config.output_dir,
#             use_gpu=config.use_gpu,
#             seed=config.seed,  #TODO: seed is not used in the controller.
#             **config.algo_config)
# rarl.load(trained_model)
# rarl.reset()
# rarl.agent.eval()
# rarl.adversary.eval()
# rarl.obs_normalizer.set_read_only()


# obs = env.reset()



# obs = rarl.obs_normalizer(obs)
# with torch.no_grad():
#     action_adv = rarl.adversary.ac.act(torch.from_numpy(obs).float())
#     print(f"The action_adv is {action_adv}")   
#     print(f"The type of the action_adv is {type(action_adv)}")  # numpy.ndarray

# # test trained rarl adversary
# env_func = QuadrotorAdversaryDistb
# rarl_ctrl = RARL(env_func=env_func, 
#                  training=False, 
#                  checkpoint_path='training_results/quadrotor_null/rarl/seed_42/10000000steps/model_latest.pt',
#                  output_dir='test_results/quadrotor_adversary', 
#                  use_gpu=False, 
#                  seed=42)

# rarl_ctrl.load(trained_model)
# rarl_ctrl.reset()



# # env = QuadrotorFixedDistb()
# env = QuadrotorBoltzDistb()
# # env = QuadrotorNullDistb()
# # env = QuadrotorRandomDistb()
env = QuadrotorAdversary()

obs = env.reset()

# for i in range(10):
#     obs = env.reset()
#     print(f"The obs is {obs}.")

# print(f"The shape of the obs is {obs.shape}")
print(f"********* The self.disturbances is {env.disturbances}. ********* \n")
print(f"********* The self.adversary_disturbance is {env.adversary_disturbance}. ********* \n")  
# print(f"********* The task is {env.TASK }. ********* \n")
# print(f"********* The self.PHYSICS is {env.PHYSICS}. ********* \n")
# print(f"********* The self.constraints is {env.constraints}. ********* \n")
# # print(f"The initial position is {env.state[0:3]}. \n")
# # print(f"The obs is {env.observation_space}")
print(f"The action is {env.action_space}")
# print(f"********** The shape of the observation space is {env.observation_space.shape}.********** \n")
print(f"********** The disturbance type is {env.distb_type}.********** \n")
# print(f"********** The disturbance level is {env.distb_level}. ********** \n")
print(f"********** The DISTURBANCE_MODES is {env.DISTURBANCE_MODES}. ********** \n")
print(f"********** The self.DISTURBANCES is {env.DISTURBANCES}. ********** \n")
print(f"********** The enable reset distribution is {env.RANDOMIZED_INIT}. ********** \n")
# print(f"********** The self.adversary_observation_space is {env.adversary_observation_space}. ********** \n")
# print(f"********** The self.adversary_action_space is {env.adversary_action_space}. ********** \n")
print(f"********** The self.observation_space is {env.observation_space}. ********** \n")
print(f"********** The self.INFO_IN_RESET is {env.INFO_IN_RESET}. ********** \n")

# # Generate gifs to check
# num_gifs = 1
# frames = [[] for _ in range(num_gifs)]
# num=0
# while num < num_gifs:
#     terminated, truncated = False, False
#     rewards = 0.0
#     steps = 0
#     max_steps=50
#     init_obs = env.reset()
#     print(f"The init_obs shape is {init_obs.shape}")
#     print(f"The initial position is {init_obs[0:3]}")
#     frames[num].append(env.render())  # the return frame is np.reshape(rgb, (h, w, 4))
    
#     for _ in range(max_steps):
#         if _ == 0:
#             obs = init_obs

#         # Select control
#         # manual control
#         motor = -0.78
#         action = np.array([motor, motor, motor, motor])  # shape: (4, )
        
#         # random control
#         # action = env.action_space.sample()

#         # # load the trained model
#         # ac, trained_env, env_distb = utils.load_actor_critic_and_env_from_disk(ckpt)
#         # ac.eval()
#         # obs = torch.as_tensor(obs, dtype=torch.float32)
#         # action, *_ = ac(obs)

#         obs, reward, done, info = env.step(action)
#         # print(f"The shape of the obs in the output of the env.step is {obs.shape}")
#         # print(f"The current reward of the step{_} is {reward} and this leads to {terminated} and {truncated}")
#         # print(f"The current penalty of the step{_} is {info['current_penalty']} and the current distance is {info['current_dist']}")
#         frames[num].append(env.render())
#         rewards += reward
#         steps += 1
        
#         if done or steps>=max_steps:
#             print(f"[INFO] Test {num} is done with rewards = {rewards} and {steps} steps.")
#             create_gif(frames[num], f'{num}-{env.NAME}-{env.distb_level}distb_level-motor{motor}-obs_noise{env.RANDOMIZED_INIT}-{steps}steps.gif', duration=0.1)
#             # print(f"The final position is {obs[0:3]}.")
#             num += 1
#             break
# env.close()



# env = Quadrotor()
# env.reset()
# # print(f"The observation space is {env.observation_space}.")
# print(f"The shape of the observation space is {env.observation_space.shape}")
# # print(f"The action is {env.action_space}")
# print(f"The shape of action space is {env.action_space.shape}. \n")

# env1 = QuadrotorBoltzDistb()
# env1.reset()
# print(f"The shape of the distb env is {env1.observation_space.shape}")
# print(f"The shape of the distb env is {env1.action_space.shape}")

# episodes = 2
# results = []

# a = np.asarray([1])

# for _ in range(episodes):

#     results.append(a[0])

# print(results)


# low = np.array([-5.3e-3, -5.3e-3, -1.43e-4])
# high = np.array([5.3e-3, 5.3e-3, 1.43e-4])

# # Generate a random sample
# sample = np.random.uniform(low, high)
# print(f"The sample is {sample}")
# print(f"The shape of the sample is {sample.shape}")

# Create the controller/control_agent.
