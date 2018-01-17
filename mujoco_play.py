#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from ddpg import parse_args, cfg_run

args = parse_args()

#env = 'Walker2d'
#env = 'HalfCheetah'
#env = 'Hopper'
#task = 'Balancing'
#task = 'Walking'

env = 'Atlas'
task = 'ForwardWalk'

if task == 'Balancing':
    task_balancing = task
else:
    task_balancing = ''

#args['cfg'] = "Roboschool{}-v1".format(env+task_balancing+'GRL')
#args['cfg'] = "Roboschool{}-v1".format(env+task_balancing)
args['cfg'] = "Roboschool{}-v1".format(env+task)

args['steps'] = 0
args['trials'] = 11
args['test_interval'] = 0
args['normalize_observations'] = False
args['normalize_returns'] = False
args['layer_norm'] = True
args['load_file'] = 'atlas_forwardwalk-best'
args['output'] = '' #'{}_{}_play'.format(env.lower(), task.lower())
args['render'] = True

# Run actual script.
args['save'] = False
cfg_run(**args)
