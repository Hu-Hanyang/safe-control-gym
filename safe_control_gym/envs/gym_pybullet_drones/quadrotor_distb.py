'''1D, 2D, and 3D quadrotor environment using PyBullet physics.

Based on UTIAS Dynamic Systems Lab's gym-pybullet-drones:
    * https://github.com/utiasDSL/gym-pybullet-drones
'''

import math
from copy import deepcopy

import casadi as cs
import numpy as np
import pybullet as p
from gymnasium import spaces

from safe_control_gym.envs.benchmark_env import Cost, Task
from safe_control_gym.envs.constraints import GENERAL_CONSTRAINTS
from safe_control_gym.envs.gym_pybullet_drones.base_distb_aviary import BaseDistbAviary
from safe_control_gym.envs.gym_pybullet_drones.quadrotor_utils import QuadType, cmd2pwm, pwm2rpm
from safe_control_gym.math_and_models.symbolic_systems import SymbolicModel
from safe_control_gym.math_and_models.transformations import csRotXYZ, transform_trajectory


class QuadrotorDistb(BaseDistbAviary):
    '''6D quadrotor environment task.

    Including symbolic model, constraints, randomization, adversarial disturbances,
    multiple cost functions, stabilization and trajectory tracking references.
    '''

    NAME = 'quadrotor_distb'
    AVAILABLE_CONSTRAINTS = deepcopy(GENERAL_CONSTRAINTS)

    DISTURBANCE_MODES = {  # Set at runtime by QUAD_TYPE
        'observation': {
            'dim': -1
        },
        'action': {
            'dim': -1
        },
        'dynamics': {
            'dim': -1
        }
    }

    INERTIAL_PROP_RAND_INFO = {
        'M': {  # Nominal: 0.027
            'distrib': 'uniform',
            'low': 0.022,
            'high': 0.032
        },
        'Ixx': {  # Nominal: 1.4e-5
            'distrib': 'uniform',
            'low': 1.3e-5,
            'high': 1.5e-5
        },
        'Iyy': {  # Nominal: 1.4e-5
            'distrib': 'uniform',
            'low': 1.3e-5,
            'high': 1.5e-5
        },
        'Izz': {  # Nominal: 2.17e-5
            'distrib': 'uniform',
            'low': 2.07e-5,
            'high': 2.27e-5
        }
    }

    INIT_STATE_RAND_INFO = {
        'init_x': {
            'distrib': 'uniform',
            'low': -0.5,
            'high': 0.5
        },
        'init_x_dot': {
            'distrib': 'uniform',
            'low': -0.01,
            'high': 0.01
        },
        'init_y': {
            'distrib': 'uniform',
            'low': -0.5,
            'high': 0.5
        },
        'init_y_dot': {
            'distrib': 'uniform',
            'low': -0.01,
            'high': 0.01
        },
        'init_z': {
            'distrib': 'uniform',
            'low': 0.1,
            'high': 1.5
        },
        'init_z_dot': {
            'distrib': 'uniform',
            'low': -0.01,
            'high': 0.01
        },
        'init_phi': {
            'distrib': 'uniform',
            'low': -0.3,
            'high': 0.3
        },
        'init_theta': {
            'distrib': 'uniform',
            'low': -0.3,
            'high': 0.3
        },
        'init_psi': {
            'distrib': 'uniform',
            'low': -0.3,
            'high': 0.3
        },
        'init_p': {
            'distrib': 'uniform',
            'low': -0.01,
            'high': 0.01
        },
        'init_theta_dot': {  # TODO: replace with q.
            'distrib': 'uniform',
            'low': -0.01,
            'high': 0.01
        },
        'init_q': {
            'distrib': 'uniform',
            'low': -0.01,
            'high': 0.01
        },
        'init_r': {
            'distrib': 'uniform',
            'low': -0.01,
            'high': 0.01
        }
    }

    TASK_INFO = {
        'stabilization_goal': [0, 1],
        'stabilization_goal_tolerance': 0.05,
        'trajectory_type': 'circle',
        'num_cycles': 1,
        'trajectory_plane': 'zx',
        'trajectory_position_offset': [0.5, 0],
        'trajectory_scale': -0.5,
        'proj_point': [0, 0, 0.5],
        'proj_normal': [0, 1, 1],
    }

    def __init__(self,
                 num_drones: int = 1,
                 record=False,
                 init_state=None,
                 inertial_prop=None,
                 # custom args
                 norm_act_scale=0.1,
                 obs_goal_horizon=0,
                 # Hanyang: initialize some important attributes disturbances parameters 
                 episode_len_sec: int = 10,
                 randomized_init: bool = True,
                 distb_type = 'fixed', 
                 distb_level: float=0.0,
                 seed=None,
                 **kwargs
                 ):
        '''Initialize a quadrotor with hj distb environment.

        Args:
            init_state (ndarray, optional): The initial state of the environment, (z, z_dot) or (x, x_dot, z, z_dot theta, theta_dot).
            inertial_prop (ndarray, optional): The inertial properties of the environment (M, Ixx, Iyy, Izz).
            quad_type (QuadType, optional): The choice of motion type (1D along z, 2D in the x-z plane, or 3D).
            norm_act_scale (float): Scaling the [-1,1] action space around hover thrust when `normalized_action_space` is True.
            obs_goal_horizon (int): How many future goal states to append to obervation.
            rew_state_weight (list/ndarray): Quadratic weights for state in rl reward.
            rew_act_weight (list/ndarray): Quadratic weights for action in rl reward.
            rew_exponential (bool): If to exponentiate negative quadratic cost to positive, bounded [0,1] reward.
            done_on_out_of_bound (bool): If to termiante when state is out of bound.
            info_mse_metric_state_weight (list/ndarray): Quadratic weights for state in mse calculation for info dict.
            episode_len_sec (int, optional): Maximum episode duration in seconds.
            randomized_init (bool, optional): Whether to randomize the initial state.
            disturbance_type (str, optional): The type of disturbance to be applied to the drones [None, 'fixed', 'boltzmann', 'random', 'rarl', 'rarl-population'].
            distb_level (float, optional): The level of disturbance to be applied to the drones.
            seed (int, optional): Seed for the random number generator.
        '''
        self.norm_act_scale = norm_act_scale
        self.obs_goal_horizon = obs_goal_horizon
       
        super().__init__(num_drones=num_drones, record=record, init_state=init_state, 
                         inertial_prop=inertial_prop, episode_len_sec=episode_len_sec, 
                         randomized_init=randomized_init,  distb_type=distb_type, 
                         distb_level=distb_level, seed=seed,
                         **kwargs)

        # Hanyang: Create X_GOAL and U_GOAL references for the assigned task.
        self.U_GOAL = np.ones(self.action_dim) * self.MASS * self.GRAVITY_ACC / self.action_dim
        if self.TASK == Task.STABILIZATION:
            self.X_GOAL = np.hstack([np.array([0.0, 0.0, 1.0, 0.0, 0.0, 0.0]) for _ in range(self.NUM_DRONES)])  # x = [x, y, z, r, p, y]
        elif self.TASK == Task.TRAJ_TRACKING:
            POS_REF, VEL_REF, _ = self._generate_trajectory(traj_type=self.TASK_INFO['trajectory_type'],
                                                    traj_length=self.EPISODE_LEN_SEC,
                                                    num_cycles=self.TASK_INFO['num_cycles'],
                                                    traj_plane=self.TASK_INFO['trajectory_plane'],
                                                    position_offset=self.TASK_INFO['trajectory_position_offset'],
                                                    scaling=self.TASK_INFO['trajectory_scale'],
                                                    sample_time=self.CTRL_TIMESTEP
                                                    )  # Each of the 3 returned values is of shape (Ctrl timesteps, 3)
      
        # Hanyang: Add some randomization parameters to initial conditions
        self.init_xy_lim = 0.25
        self.init_z_lim = 0.1
        self.init_rp_lim = np.pi/6
        self.init_y_lim = 2*np.pi
        self.init_vel_lim = 0.1
        self.init_rp_vel_lim = 200 * self.DEG2RAD
        self.init_y_vel_lim = 20 * self.DEG2RAD
        
        # Hanyang: Set the limits for termination (get_done)
        self.rp_limit = 75 * self.DEG2RAD  # rad
        self.rpy_dot_limit = 1000 * self.DEG2RAD  # rad/s
        self.z_lim = 0.1  # m
        
        # Hanyang: Set the penalties for rewards (get_reward)
        self.penalty_action =1e-4
        self.penalty_angle = 1e-2
        self.penalty_angle_rate = 1e-3
        self.penalty_terminal = 100
        
        # Set prior/symbolic info.
        self._setup_symbolic()


    def reset(self, seed=None):
        '''(Re-)initializes the environment to start an episode.

        Mandatory to call at least once after __init__().

        Args:
            seed (int): An optional seed to reseed the environment.

        Returns:
            obs (ndarray): The initial state of the environment.
            info (dict): A dictionary with information about the dynamics and constraints symbolic models.
        '''

        super().before_reset(seed=seed)
        # PyBullet simulation reset.
        super()._reset_simulation()

        # Hanyang: Add some randomization to initial conditions
        if self.RANDOMIZED_INIT:
            for id in range(self.NUM_DRONES):
                self.pos[id] += np.random.uniform(-self.init_xy_lim, self.init_xy_lim, 3)

                self.rpy[id] += np.random.uniform(-self.init_rp_lim, self.init_rp_lim, 3)
                self.rpy[id][2] = np.random.uniform(-self.init_y_lim, self.init_y_lim)
                self.quat[id] = p.getQuaternionFromEuler(self.rpy[id])

                self.vel[id] += np.random.uniform(-self.init_vel_lim, self.init_vel_lim, 3)

                self.ang_v[id] += np.random.uniform(-self.init_rp_vel_lim, self.init_rp_vel_lim, 3)
                self.ang_v[id][2] = np.random.uniform(-self.init_y_vel_lim, self.init_y_vel_lim)
            # Hanyang: Connect to PyBullet ###################################
            for id in range(self.NUM_DRONES):
                p.resetBasePositionAndOrientation(self.DRONE_IDS[id], posObj=self.pos[id], ornObj=self.quat[id], physicsClientId=self.PYB_CLIENT)
                R = np.array(p.getMatrixFromQuaternion(self.quat[id])).reshape(3, 3)
                p.resetBaseVelocity(self.DRONE_IDS[id], linearVelocity=self.vel[id], angularVelocity=R.T@self.ang_v[id], physicsClientId=self.PYB_CLIENT)
        
        # Update BaseAviary internal variables before calling self._get_observation().
        self._update_and_store_kinematic_information()
        obs, info = self._get_observation(), self._get_reset_info()
        obs, info = super().after_reset(obs, info)

        # Return either an observation and dictionary or just the observation.
        if self.INFO_IN_RESET:
            return obs, info
        else:
            return obs

    def step(self, action):
        '''Advances the environment by one control step.

        Pass the commanded RPMs and the adversarial force to the superclass .step().
        The PyBullet simulation is stepped PYB_FREQ/CTRL_FREQ times in BaseAviary.

        Args:
            action (ndarray): The action returned by the controller.

        Returns:
            obs (ndarray): The state of the environment after the step.
            reward (float): The scalar reward/cost of the step.
            done (bool): Whether the conditions for the end of an episode are met in the step.
            info (dict): A dictionary with information about the constraints evaluations and violations.
        '''

        # Get the preprocessed pwm for each motor
        pwm = super().before_step(action)

        # Determine disturbance force.
        disturb_force = None
        # passive_disturb = 'dynamics' in self.disturbances
        # adv_disturb = self.adversary_disturbance == 'dynamics'
        # if passive_disturb or adv_disturb:
        #     disturb_force = np.zeros(self.DISTURBANCE_MODES['dynamics']['dim'])
        # if passive_disturb:
        #     disturb_force = self.disturbances['dynamics'].apply(
        #         disturb_force, self)
        # if adv_disturb and self.adv_action is not None:
        #     disturb_force = disturb_force + self.adv_action
        #     # Clear the adversary action, wait for the next one.
        #     self.adv_action = None
        # #TODO: Hanyang: need to revise the shape of the disturb_force here
        # #TODO: Hanyang: it should be a 4-dimensional vector?
        # # Construct full (3D) disturbance force.
        # if disturb_force is not None:
        #     disturb_force = np.asarray(disturb_force)
            # if self.QUAD_TYPE == QuadType.ONE_D:
            #     # Only disturb on z direction.
            #     disturb_force = [0, 0, float(disturb_force)]
            # elif self.QUAD_TYPE == QuadType.TWO_D:
            #     # Only disturb on x-z plane.
            #     disturb_force = [float(disturb_force[0]), 0, float(disturb_force[1])]
            # elif self.QUAD_TYPE == QuadType.THREE_D:
            #     disturb_force = np.asarray(disturb_force).flatten()

        # Advance the simulation.
        super()._advance_simulation(pwm, disturb_force)
        # Standard Gym return.
        # Hanyang: revise the following code to get the obs, rew, done, info
        obs = self._get_observation()
        rew = self._get_reward(action)
        done = self._get_done()
        info = self._get_info()
        obs, rew, done, info = super().after_step(obs, rew, done, info)
        # Hanyang: log the action generated by the policy network
        self.last_action = action.copy()
        return obs, rew, done, info

    def render(self, mode='human'):
        '''Retrieves a frame from PyBullet rendering.

        Args:
            mode (str): Unused.

        Returns:
            frame (ndarray): A multidimensional array with the RGB frame captured by PyBullet's camera.
        '''

        [w, h, rgb, _, _] = p.getCameraImage(width=self.RENDER_WIDTH,
                                             height=self.RENDER_HEIGHT,
                                             shadow=1,
                                             viewMatrix=self.CAM_VIEW,
                                             projectionMatrix=self.CAM_PRO,
                                             renderer=p.ER_TINY_RENDERER,
                                             flags=p.ER_SEGMENTATION_MASK_OBJECT_AND_LINKINDEX,
                                             physicsClientId=self.PYB_CLIENT)
        # Image.fromarray(np.reshape(rgb, (h, w, 4)), 'RGBA').show()
        return np.reshape(rgb, (h, w, 4))

    def _setup_symbolic(self, prior_prop={}, **kwargs):
        #TODO: Hanyang: not implemented 6D dynamics yet
        '''Creates symbolic (CasADi) models for dynamics, observation, and cost.

        Args:
            prior_prop (dict): specify the prior inertial prop to use in the symbolic model.
        '''
        m = prior_prop.get('M', self.MASS)
        Iyy = prior_prop.get('Iyy', self.J[1, 1])
        g, length = self.GRAVITY_ACC, self.L
        dt = self.CTRL_TIMESTEP
        # Define states.
        z = cs.MX.sym('z')
        z_dot = cs.MX.sym('z_dot')
        u_eq = m * g
        # if self.QUAD_TYPE == QuadType.ONE_D:
        #     nx, nu = 2, 1
        #     # Define states.
        #     X = cs.vertcat(z, z_dot)
        #     # Define input thrust.
        #     T = cs.MX.sym('T')
        #     U = cs.vertcat(T)
        #     # Define dynamics equations.
        #     X_dot = cs.vertcat(z_dot, T / m - g)
        #     # Define observation equation.
        #     Y = cs.vertcat(z, z_dot)
        # elif self.QUAD_TYPE == QuadType.TWO_D:
        #     nx, nu = 6, 2
        #     # Define states.
        #     x = cs.MX.sym('x')
        #     x_dot = cs.MX.sym('x_dot')
        #     theta = cs.MX.sym('theta')
        #     theta_dot = cs.MX.sym('theta_dot')
        #     X = cs.vertcat(x, x_dot, z, z_dot, theta, theta_dot)
        #     # Define input thrusts.
        #     T1 = cs.MX.sym('T1')
        #     T2 = cs.MX.sym('T2')
        #     U = cs.vertcat(T1, T2)
        #     # Define dynamics equations.
        #     X_dot = cs.vertcat(x_dot,
        #                        cs.sin(theta) * (T1 + T2) / m, z_dot,
        #                        cs.cos(theta) * (T1 + T2) / m - g, theta_dot,
        #                        length * (T2 - T1) / Iyy / np.sqrt(2))
        #     # Define observation.
        #     Y = cs.vertcat(x, x_dot, z, z_dot, theta, theta_dot)
        # elif self.QUAD_TYPE == QuadType.THREE_D:
        nx, nu = 12, 4
        Ixx = prior_prop.get('Ixx', self.J[0, 0])
        Izz = prior_prop.get('Izz', self.J[2, 2])
        J = cs.blockcat([[Ixx, 0.0, 0.0],
                            [0.0, Iyy, 0.0],
                            [0.0, 0.0, Izz]])
        Jinv = cs.blockcat([[1.0 / Ixx, 0.0, 0.0],
                            [0.0, 1.0 / Iyy, 0.0],
                            [0.0, 0.0, 1.0 / Izz]])
        gamma = self.KM / self.KF
        x = cs.MX.sym('x')
        y = cs.MX.sym('y')
        phi = cs.MX.sym('phi')  # Roll
        theta = cs.MX.sym('theta')  # Pitch
        psi = cs.MX.sym('psi')  # Yaw
        x_dot = cs.MX.sym('x_dot')
        y_dot = cs.MX.sym('y_dot')
        p_body = cs.MX.sym('p')  # Body frame roll rate
        q_body = cs.MX.sym('q')  # body frame pith rate
        r_body = cs.MX.sym('r')  # body frame yaw rate
        # PyBullet Euler angles use the SDFormat for rotation matrices.
        Rob = csRotXYZ(phi, theta, psi)  # rotation matrix transforming a vector in the body frame to the world frame.

        # Define state variables.
        X = cs.vertcat(x, x_dot, y, y_dot, z, z_dot, phi, theta, psi, p_body, q_body, r_body)

        # Define inputs.
        f1 = cs.MX.sym('f1')
        f2 = cs.MX.sym('f2')
        f3 = cs.MX.sym('f3')
        f4 = cs.MX.sym('f4')
        U = cs.vertcat(f1, f2, f3, f4)

        # From Ch. 2 of Luis, Carlos, and Jérôme Le Ny. 'Design of a trajectory tracking controller for a
        # nanoquadcopter.' arXiv preprint arXiv:1608.05786 (2016).

        # Defining the dynamics function.
        # We are using the velocity of the base wrt to the world frame expressed in the world frame.
        # Note that the reference expresses this in the body frame.
        oVdot_cg_o = Rob @ cs.vertcat(0, 0, f1 + f2 + f3 + f4) / m - cs.vertcat(0, 0, g)
        pos_ddot = oVdot_cg_o
        pos_dot = cs.vertcat(x_dot, y_dot, z_dot)
        Mb = cs.vertcat(length / cs.sqrt(2.0) * (f1 + f2 - f3 - f4),
                        length / cs.sqrt(2.0) * (-f1 + f2 + f3 - f4),
                        gamma * (-f1 + f2 - f3 + f4))
        rate_dot = Jinv @ (Mb - (cs.skew(cs.vertcat(p_body, q_body, r_body)) @ J @ cs.vertcat(p_body, q_body, r_body)))
        ang_dot = cs.blockcat([[1, cs.sin(phi) * cs.tan(theta), cs.cos(phi) * cs.tan(theta)],
                                [0, cs.cos(phi), -cs.sin(phi)],
                                [0, cs.sin(phi) / cs.cos(theta), cs.cos(phi) / cs.cos(theta)]]) @ cs.vertcat(p_body, q_body, r_body)
        X_dot = cs.vertcat(pos_dot[0], pos_ddot[0], pos_dot[1], pos_ddot[1], pos_dot[2], pos_ddot[2], ang_dot, rate_dot)

        Y = cs.vertcat(x, x_dot, y, y_dot, z, z_dot, phi, theta, psi, p_body, q_body, r_body)
        # Set the equilibrium values for linearizations.
        X_EQ = np.zeros(self.state_dim)
        U_EQ = np.ones(self.action_dim) * u_eq / self.action_dim
        # Define cost (quadratic form).
        Q = cs.MX.sym('Q', nx, nx)
        R = cs.MX.sym('R', nu, nu)
        Xr = cs.MX.sym('Xr', nx, 1)
        Ur = cs.MX.sym('Ur', nu, 1)
        cost_func = 0.5 * (X - Xr).T @ Q @ (X - Xr) + 0.5 * (U - Ur).T @ R @ (U - Ur)
        # Define dynamics and cost dictionaries.
        dynamics = {'dyn_eqn': X_dot, 'obs_eqn': Y, 'vars': {'X': X, 'U': U}}
        cost = {
            'cost_func': cost_func,
            'vars': {
                'X': X,
                'U': U,
                'Xr': Xr,
                'Ur': Ur,
                'Q': Q,
                'R': R
            }
        }
        # Additional params to cache
        params = {
            # prior inertial properties
            'quad_mass': m,
            'quad_Iyy': Iyy,
            'quad_Ixx': Ixx if 'Ixx' in locals() else None,
            'quad_Izz': Izz if 'Izz' in locals() else None,
            # equilibrium point for linearization
            'X_EQ': X_EQ,
            'U_EQ': U_EQ,
        }
        # Setup symbolic model.
        self.symbolic = SymbolicModel(dynamics=dynamics, cost=cost, dt=dt, params=params)

    def _set_action_space(self):
        '''Sets the action space of the environment.'''
        # Define action/input dimension, labels, and units.
        # if self.QUAD_TYPE == QuadType.ONE_D:
        #     action_dim = 1
        #     self.ACTION_LABELS = ['T']
        #     self.ACTION_UNITS = ['N'] if not self.NORMALIZED_RL_ACTION_SPACE else ['-']
        # elif self.QUAD_TYPE == QuadType.TWO_D:
        #     action_dim = 2
        #     self.ACTION_LABELS = ['T1', 'T2']
        #     self.ACTION_UNITS = ['N', 'N'] if not self.NORMALIZED_RL_ACTION_SPACE else ['-', '-']
        # elif self.QUAD_TYPE == QuadType.THREE_D:
        #     action_dim = 4
        #     self.ACTION_LABELS = ['T1', 'T2', 'T3', 'T4']
        #     self.ACTION_UNITS = ['N', 'N', 'N', 'N'] if not self.NORMALIZED_RL_ACTION_SPACE else ['-', '-', '-', '-']
        # # Hanyang: add the action space for 6D quadrotor
        # elif self.QUAD_TYPE == QuadType.SIX_D:
        action_dim = 4
        act_lower_bound = np.array([-1*np.ones(action_dim) for i in range(self.NUM_DRONES)])
        act_upper_bound = np.array([+1*np.ones(action_dim) for i in range(self.NUM_DRONES)])

        # n_mot = 4 / action_dim
        # a_low = self.KF * n_mot * (self.PWM2RPM_SCALE * self.MIN_PWM + self.PWM2RPM_CONST)**2
        # a_high = self.KF * n_mot * (self.PWM2RPM_SCALE * self.MAX_PWM + self.PWM2RPM_CONST)**2
        # self.physical_action_bounds = (np.full(action_dim, a_low, np.float32),
        #                                np.full(action_dim, a_high, np.float32))

        # if self.NORMALIZED_RL_ACTION_SPACE:
        #     # Normalized thrust (around hover thrust).
        #     self.hover_thrust = self.GRAVITY_ACC * self.MASS / action_dim
        #     self.action_space = spaces.Box(low=-np.ones(action_dim),
        #                                    high=np.ones(action_dim),
        #                                    dtype=np.float32)
        # else:
        #     # Direct thrust control.
        #         self.action_space = spaces.Box(low=self.physical_action_bounds[0],
        #                                     high=self.physical_action_bounds[1],
        #                                     dtype=np.float32)
        # Hanyang: define the action space for 6D quadrotor
        self.action_space = spaces.Box(low=act_lower_bound, high=act_upper_bound, dtype=np.float32)

    def _set_observation_space(self):
        # '''Sets the observation space of the environment.'''
        # self.x_threshold = 2
        # self.y_threshold = 2
        # self.z_threshold = 2
        # self.phi_threshold_radians = 85 * math.pi / 180
        # self.theta_threshold_radians = 85 * math.pi / 180
        # self.psi_threshold_radians = 180 * math.pi / 180  # Do not bound yaw.

        # # Define obs/state bounds, labels and units.
        # if self.QUAD_TYPE == QuadType.ONE_D:
        #     # obs/state = {z, z_dot}.
        #     low = np.array([self.GROUND_PLANE_Z, -np.finfo(np.float32).max])
        #     high = np.array([self.z_threshold, np.finfo(np.float32).max])
        #     self.STATE_LABELS = ['z', 'z_dot']
        #     self.STATE_UNITS = ['m', 'm/s']
        # elif self.QUAD_TYPE == QuadType.TWO_D:
        #     # obs/state = {x, x_dot, z, z_dot, theta, theta_dot}.
        #     low = np.array([
        #         -self.x_threshold, -np.finfo(np.float32).max,
        #         self.GROUND_PLANE_Z, -np.finfo(np.float32).max,
        #         -self.theta_threshold_radians, -np.finfo(np.float32).max
        #     ])
        #     high = np.array([
        #         self.x_threshold, np.finfo(np.float32).max,
        #         self.z_threshold, np.finfo(np.float32).max,
        #         self.theta_threshold_radians, np.finfo(np.float32).max
        #     ])
        #     self.STATE_LABELS = ['x', 'x_dot', 'z', 'z_dot', 'theta', 'theta_dot']
        #     self.STATE_UNITS = ['m', 'm/s', 'm', 'm/s', 'rad', 'rad/s']
        # elif self.QUAD_TYPE == QuadType.THREE_D:
        #     # obs/state = {x, x_dot, y, y_dot, z, z_dot, phi, theta, psi, p_body, q_body, r_body}.
        #     low = np.array([
        #         -self.x_threshold, -np.finfo(np.float32).max,
        #         -self.y_threshold, -np.finfo(np.float32).max,
        #         self.GROUND_PLANE_Z, -np.finfo(np.float32).max,
        #         -self.phi_threshold_radians, -self.theta_threshold_radians, -self.psi_threshold_radians,
        #         -np.finfo(np.float32).max, -np.finfo(np.float32).max, -np.finfo(np.float32).max
        #     ])
        #     high = np.array([
        #         self.x_threshold, np.finfo(np.float32).max,
        #         self.y_threshold, np.finfo(np.float32).max,
        #         self.z_threshold, np.finfo(np.float32).max,
        #         self.phi_threshold_radians, self.theta_threshold_radians, self.psi_threshold_radians,
        #         np.finfo(np.float32).max, np.finfo(np.float32).max, np.finfo(np.float32).max
        #     ])
        #     self.STATE_LABELS = ['x', 'x_dot', 'y', 'y_dot', 'z', 'z_dot',
        #                          'phi', 'theta', 'psi', 'p', 'q', 'r']
        #     self.STATE_UNITS = ['m', 'm/s', 'm', 'm/s', 'm', 'm/s',
        #                         'rad', 'rad', 'rad', 'rad/s', 'rad/s', 'rad/s']
        
        #### OBS SPACE OF SIZE 17
        #### Observation vector ### pos, quat, vel, ang_v, last_clipped_action
        lo = -np.inf
        hi = np.inf

        obs_lower_bound = np.array([[lo,lo,0, lo,lo,lo,lo, lo,lo,lo, lo,lo,lo] for i in range(self.NUM_DRONES)])
        obs_upper_bound = np.array([[hi,hi,hi, hi,hi,hi,hi, hi,hi,hi, hi,hi,hi] for i in range(self.NUM_DRONES)])
        #### Add action buffer to observation space ################
        act_lo = -1
        act_hi = +1
        obs_lower_bound = np.hstack([obs_lower_bound, np.array([[act_lo,act_lo,act_lo,act_lo] for i in range(self.NUM_DRONES)])])
        obs_upper_bound = np.hstack([obs_upper_bound, np.array([[act_hi,act_hi,act_hi,act_hi] for i in range(self.NUM_DRONES)])])
        # Define the state space for the dynamics.
        self.state_space = spaces.Box(low=obs_lower_bound, high=obs_upper_bound, dtype=np.float32)

        # Concatenate reference for RL.
        # if self.COST == Cost.RL_REWARD and self.TASK == Task.TRAJ_TRACKING and self.obs_goal_horizon > 0:
        #     # Include future goal state(s).
        #     # e.g. horizon=1, obs = {state, state_target}
        #     mul = 1 + self.obs_goal_horizon
        #     low = np.concatenate([low] * mul)
        #     high = np.concatenate([high] * mul)
        # elif self.COST == Cost.RL_REWARD and self.TASK == Task.STABILIZATION and self.obs_goal_horizon > 0:
        #     low = np.concatenate([low] * 2)
        #     high = np.concatenate([high] * 2)

        # Define obs space exposed to the controller.
        # Note how the obs space can differ from state space (i.e. augmented with the next reference states for RL)
        self.observation_space = spaces.Box(low=obs_lower_bound, high=obs_upper_bound, dtype=np.float32)

    def _setup_disturbances(self):
        '''Sets up the disturbances.'''
        # Custom disturbance info.
        self.DISTURBANCE_MODES['observation']['dim'] = self.obs_dim
        self.DISTURBANCE_MODES['action']['dim'] = self.action_dim
        # self.DISTURBANCE_MODES['dynamics']['dim'] = int(self.QUAD_TYPE)
        self.DISTURBANCE_MODES['dynamics']['dim'] = 6
        
        super()._setup_disturbances()

    def _preprocess_control(self, action):
        '''Converts the action passed to .step() into motors' PWMs (ndarray of shape (4,)).

        Args:
            action (ndarray): The raw action input, of shape (4,).

        Returns:
            action (ndarray): The motors PWMs to apply to the quadrotor.
        '''
        action = self.denormalize_action(action)  # Hanayng: this line doesn't work actually
        self.current_physical_action = action

        # Apply disturbances.
        if 'action' in self.disturbances:
            action = self.disturbances['action'].apply(action, self)
        if self.adversary_disturbance == 'action':
            action = action + self.adv_action
        self.current_noisy_physical_action = action
        
        #TODO: Hanyang: calculate PWM values, need to check the shape here
        pwm = 30000 + np.clip(action, -1, +1) * 30000

        # thrust = np.clip(action, self.physical_action_bounds[0], self.physical_action_bounds[1])
        # self.current_clipped_action = thrust

        # # convert to quad motor rpm commands
        # pwm = cmd2pwm(thrust, self.PWM2RPM_SCALE, self.PWM2RPM_CONST, self.KF, self.MIN_PWM, self.MAX_PWM)
        # rpm = pwm2rpm(pwm, self.PWM2RPM_SCALE, self.PWM2RPM_CONST)
        return pwm

    def normalize_action(self, action):
        '''Converts a physical action into an normalized action if necessary.

        Args:
            action (ndarray): The action to be converted.

        Returns:
            normalized_action (ndarray): The action in the correct action space.
        '''
        if self.NORMALIZED_RL_ACTION_SPACE:  # Hanyang: NORMALIZED_RL_ACTION_SPACE is set to False default
            action = (action / self.hover_thrust - 1) / self.norm_act_scale

        return action

    def denormalize_action(self, action):
        '''Converts a normalized action into a physical action if necessary.

        Args:
            action (ndarray): The action to be converted.

        Returns:
            physical_action (ndarray): The physical action.
        '''
        if self.NORMALIZED_RL_ACTION_SPACE:
            action = (1 + self.norm_act_scale * action) * self.hover_thrust

        return action

    def _get_observation(self):
        '''Returns the current observation (state) of the environment.

        Returns:
            obs (ndarray): The state of the quadrotor, of size 17 depending on QUAD_TYPE.
        '''
        #TODO: Hanyang: it seems now it only supports 1 drone due to the observation disturbance
        full_state = self._get_drone_state_vector(0)  
        # pos, _, rpy, vel, ang_v, _ = np.split(full_state, [3, 7, 10, 13, 16])
        # if self.QUAD_TYPE == QuadType.ONE_D:
        #     # {z, z_dot}.
        #     self.state = np.hstack([pos[2], vel[2]]).reshape((2,))
        # elif self.QUAD_TYPE == QuadType.TWO_D:
        #     # {x, x_dot, z, z_dot, theta, theta_dot}.
        #     self.state = np.hstack(
        #         [pos[0], vel[0], pos[2], vel[2], rpy[1], ang_v[1]]
        #     ).reshape((6,))
        # elif self.QUAD_TYPE == QuadType.THREE_D:
        #     Rob = np.array(p.getMatrixFromQuaternion(self.quat[0])).reshape((3, 3))
        #     Rbo = Rob.T
        #     ang_v_body_frame = Rbo @ ang_v
        #     # {x, x_dot, y, y_dot, z, z_dot, phi, theta, psi, p_body, q_body, r_body}.
        #     self.state = np.hstack(
        #         # [pos[0], vel[0], pos[1], vel[1], pos[2], vel[2], rpy, ang_v]  # Note: world ang_v != body frame pqr
        #         [pos[0], vel[0], pos[1], vel[1], pos[2], vel[2], rpy, ang_v_body_frame]
        #     ).reshape((12,))
        # # Hanyang: add the six dynamics
        # elif self.QUAD_TYPE == QuadType.SIX_D:
            # {pos(xyz), quaternion, rpy, velocity, angular_velocity, last_action}.
        self.state = np.hstack([full_state[0:3], full_state[3:7], full_state[10:13], full_state[13:16], full_state[16:20]]).reshape(17,)
        # print(f"The shape of the return of the method _get_observation is {self.state.shape}. \n")
        # Apply observation disturbance.
        full_state = deepcopy(self.state)
        if 'observation' in self.disturbances:
            full_state = self.disturbances['observation'].apply(full_state, self)

        # Concatenate goal info (references state(s)) for RL.
        # Plus two because ctrl_step_counter has not incremented yet, and we want to return the obs (which would be
        # ctrl_step_counter + 1 as the action has already been applied), and the next state (+ 2) for the RL to see
        # the next state.
        # if self.at_reset:
        #     full_state = self.extend_obs(full_state, 1)
        # else:
        #     full_state = self.extend_obs(full_state, self.ctrl_step_counter + 2)
        return full_state

    def _get_reward(self, action):
        '''Computes the current step's reward value.
        
        Args:
            action (ndarray): The action generated by the controller.

        Returns:
            reward (float): The evaluated reward/cost.
        '''
        # RL cost.
        assert self.COST == Cost.RL_REWARD, print("Now we only support RL_REWARD. \n")
        state = self.state  # (17,)
        normed_clipped_a = 0.5 * (np.clip(action, -1, 1) + 1)
        penalty_action = self.penalty_action * np.linalg.norm(normed_clipped_a)
        # penalty_rpy = self.penalty_angle * np.linalg.norm(state[7:10])
        penalty_rpy_dot = self.penalty_angle_rate * np.linalg.norm(state[13:16])
        penalty_terminal = self.penalty_terminal if self._get_done() else 0.  # Hanyang: try larger crash penalty

        # penalties = np.sum([penalty_action, penalty_rpy, penalty_rpy_dot, penalty_terminal])
        penalties = np.sum([penalty_action, penalty_rpy_dot, penalty_terminal])

        dist = np.linalg.norm(state[0:3] - self.TARGET_POS)
        reward = -dist - penalties
            
        # act = np.asarray(self.current_noisy_physical_action)
        # act_error = act - self.U_GOAL
        # # Quadratic costs w.r.t state and action
        # # TODO: consider using multiple future goal states for cost in tracking
        # if self.TASK == Task.STABILIZATION:
        #     state_error = state - self.X_GOAL
        #     dist = np.sum(self.rew_state_weight * state_error * state_error)
        #     dist += np.sum(self.rew_act_weight * act_error * act_error)
        # if self.TASK == Task.TRAJ_TRACKING:
        #     wp_idx = min(self.ctrl_step_counter + 1, self.X_GOAL.shape[0] - 1)  # +1 because state has already advanced but counter not incremented.
        #     state_error = state - self.X_GOAL[wp_idx]
        #     dist = np.sum(self.rew_state_weight * state_error * state_error)
        #     dist += np.sum(self.rew_act_weight * act_error * act_error)
        # rew = -dist
        # # Convert rew to be positive and bounded [0,1].
        # if self.rew_exponential:
        #     rew = np.exp(rew)
        return reward

        # # Control cost.
        # if self.COST == Cost.QUADRATIC:
        #     if self.TASK == Task.STABILIZATION:
        #         return float(-1 * self.symbolic.loss(x=self.state,
        #                                              Xr=self.X_GOAL,
        #                                              u=self.current_clipped_action,
        #                                              Ur=self.U_GOAL,
        #                                              Q=self.Q,
        #                                              R=self.R)['l'])
        #     if self.TASK == Task.TRAJ_TRACKING:
        #         return float(-1 * self.symbolic.loss(x=self.state,
        #                                              Xr=self.X_GOAL[self.ctrl_step_counter + 1, :],  # +1 because state has already advanced but counter not incremented.
        #                                              u=self.current_clipped_action,
        #                                              Ur=self.U_GOAL,
        #                                              Q=self.Q,
        #                                              R=self.R)['l'])

    def _get_done(self):
        '''Computes the conditions for termination of an episode.

        Returns:
            done (bool): Whether an episode is over.
        '''
        # # Done if goal reached for stabilization task with quadratic cost.
        # if self.TASK == Task.STABILIZATION:
        #     self.goal_reached = bool(np.linalg.norm(self.state - self.X_GOAL) < self.TASK_INFO['stabilization_goal_tolerance'])
        #     if self.goal_reached:
        #         return True

        # # Done if state is out-of-bounds.
        # if self.done_on_out_of_bound:
        #     if self.QUAD_TYPE == QuadType.ONE_D:
        #         mask = np.array([1, 0])
        #     if self.QUAD_TYPE == QuadType.TWO_D:
        #         mask = np.array([1, 0, 1, 0, 1, 0])
        #     if self.QUAD_TYPE == QuadType.THREE_D:
        #         mask = np.array([1, 0, 1, 0, 1, 0, 1, 1, 1, 0, 0, 0])
        #     # Element-wise or to check out-of-bound conditions.
        #     self.out_of_bounds = np.logical_or(self.state < self.state_space.low,
        #                                        self.state > self.state_space.high)
        #     # Mask out un-included dimensions (i.e. velocities)
        #     self.out_of_bounds = np.any(self.out_of_bounds * mask)
        #     # Early terminate if needed.
        #     if self.out_of_bounds:
        #         return True
        # self.out_of_bounds = False
        state = self.state  # (17,)
        rp = state[7:9]  # rad
        rp_limit = rp[np.abs(rp) > self.rp_limit].any()
        
        rpy_dot = state[13:16]  # rad/s
        rpy_dot_limit = rpy_dot[np.abs(rpy_dot) > self.rpy_dot_limit].any()
        
        z = state[2]  # m
        z_limit = z < self.z_lim

        # done = True if position_limit or rp_limit or rpy_dot_limit or z_limit else False
        done = True if rp_limit or rpy_dot_limit or z_limit else False
        
        if done:
            self.out_of_bounds = True
        
        return done

    def _get_info(self):
        '''Generates the info dictionary returned by every call to .step().

        Returns:
            info (dict): A dictionary with information about the constraints evaluations and violations.
        '''
        info = {}
        if self.TASK == Task.STABILIZATION and self.COST == Cost.QUADRATIC:
            info['goal_reached'] = self.goal_reached  # Add boolean flag for the goal being reached.
        # if self.done_on_out_of_bound:
        info['out_of_bounds'] = self.out_of_bounds
        # Add MSE.
        state = deepcopy(self.state)
        if self.TASK == Task.STABILIZATION:
            xyz_rpy = np.concatenate([state[0:3], state[7:10]])
            state_error = xyz_rpy - self.X_GOAL[0]
        elif self.TASK == Task.TRAJ_TRACKING:
            # state[4] = normalize_angle(state[4])
            wp_idx = min(self.ctrl_step_counter + 1, self.X_GOAL.shape[0] - 1)  # +1 so that state is being compared with proper reference state.
            state_error = state - self.X_GOAL[wp_idx]
        # Filter only relevant dimensions.
        state_error = state_error 
        info['mse'] = np.sum(state_error ** 2)
        # Hanyang: add more info
        info['current_episode_distb_level'] = self.distb_level
        # if self.constraints is not None:
        #     info['constraint_values'] = self.constraints.get_values(self)
        #     info['constraint_violations'] = self.constraints.get_violations(self)
        return info

    def _get_reset_info(self):
        '''Generates the info dictionary returned by every call to .reset().

        Returns:
            info (dict): A dictionary with information about the dynamics and constraints symbolic models.
        '''
        info = {}
        state = deepcopy(self.state)
        if self.TASK == Task.STABILIZATION:
            xyz_rpy = np.concatenate([state[0:3], state[7:10]])
            state_error = xyz_rpy - self.X_GOAL[0]
        elif self.TASK == Task.TRAJ_TRACKING:
            # state[4] = normalize_angle(state[4])
            wp_idx = min(self.ctrl_step_counter + 1, self.X_GOAL.shape[0] - 1)  # +1 so that state is being compared with proper reference state.
            state_error = state - self.X_GOAL[wp_idx]
        # Filter only relevant dimensions.
        state_error = state_error 
        info['mse'] = np.sum(state_error ** 2)
        # Hanyang: add more info
        info['current_episode_distb_level'] = self.distb_level
        info['initial_state'] = state
        info['initial_position'] = state[0:3]
        info['initial_rpy'] = state[7:10]
        info['initial_velocity'] = state[10:13]
        # info['symbolic_model'] = self.symbolic
        # info['physical_parameters'] = {
        #     'quadrotor_mass': self.OVERRIDDEN_QUAD_MASS,
        #     'quadrotor_inertia': self.OVERRIDDEN_QUAD_INERTIA,
        # }
        # info['x_reference'] = self.X_GOAL
        # info['u_reference'] = self.U_GOAL
        if self.constraints is not None:
            info['symbolic_constraints'] = self.constraints.get_all_symbolic_models()
        return info


class QuadrotorFixedDistb(QuadrotorDistb):
    NAME = 'quadrotor_fixed'
    def __init__(self, *args,  **kwargs):  # distb_level=1.0, randomization_reset=False,
        # Set disturbance_type to 'fixed' regardless of the input
        kwargs['distb_type'] = 'fixed'
        kwargs['distb_level'] = 1.0
        kwargs['randomized_init'] = True
        kwargs['record'] = True
        kwargs['seed'] = 42
        super().__init__(*args, **kwargs)  # distb_level=distb_level, randomization_reset=randomization_reset,


class QuadrotorBoltzDistb(QuadrotorDistb):
    NAME = 'quadrotor_boltz'
    def __init__(self, *args,  **kwargs):  # distb_level=1.0, randomization_reset=False,
        # Set disturbance_type to 'fixed' regardless of the input
        kwargs['distb_type'] = 'boltzmann'
        kwargs['distb_level'] = 0.0
        kwargs['randomized_init'] = True
        kwargs['record'] = True
        kwargs['seed'] = 42
        super().__init__(*args, **kwargs)  # distb_level=distb_level, randomization_reset=randomization_reset,

class QuadrotorNullDistb(QuadrotorDistb):
    NAME = 'quadrotor_null'
    def __init__(self, *args,  **kwargs):  # distb_level=1.0, randomization_reset=False,
        # Set disturbance_type to 'fixed' regardless of the input
        kwargs['distb_type'] = 'fixed'
        kwargs['distb_level'] = 0.0
        kwargs['randomized_init'] = True
        kwargs['record'] = True
        kwargs['seed'] = 42
        super().__init__(*args, **kwargs)  # distb_level=distb_level, randomization_reset=randomization_reset,