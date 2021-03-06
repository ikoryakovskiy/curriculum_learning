#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from ddpg import parse_args, cfg_run

args = parse_args()

#env = 'Walker2d'
env = 'HalfCheetah'
#env = 'Hopper'
#task = 'Balancing'
task = 'Walking'

#env = 'Atlas'
#task = 'ForwardWalk'

if task == 'Balancing':
    task_balancing = task
else:
    task_balancing = ''

args['cfg'] = "Roboschool{}-v1".format(env+task_balancing+'GRL')
#args['cfg'] = "Roboschool{}-v1".format(env+task_balancing)
#args['cfg'] = "Roboschool{}-v1".format(env+task)
args['steps'] = 20
args['test_interval'] = 30
args['seed'] = 1
args['rb_max_size'] = args['steps']
args['normalize_observations'] = False
args['normalize_returns'] = False
args['batch_norm'] = True
args['version'] = 0
args['output'] = 'cl/{}_{}'.format(env.lower(), task.lower())

#args['rb_save_filename'] = 'cl/{}_{}'.format(env.lower(), task.lower())
args['rb_load_filename'] = 'cl/{}_{}'.format(env.lower(), 'balancing')
args['reassess_for'] = 'walking_3_-1.5'

# Run actual script.
args['save'] = True
cfg_run(**args)
