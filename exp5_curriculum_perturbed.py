#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from multiprocessing import cpu_count
from ddpg import parse_args
from cl_learning import Helper, prepare_multiprocessing, do_multiprocessing_pool
import random
import yaml, collections, io
from cl_main import cl_run
import numpy as np
import os
import sys

def main():
    args = parse_args()

    if args['cores']:
        cores = min(cpu_count(), args['cores'])
    else:
        cores = min(cpu_count(), 16)
    print('Using {} cores.'.format(cores))

    # for working with yaml files
    _mapping_tag = yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG
    yaml.add_representer(collections.OrderedDict, dict_representer)
    yaml.add_constructor(_mapping_tag, dict_constructor)

    # Parameters
    runs = range(16)

    # create perturbed models of leo
    model_paths = (
            '/home/ivan/work/Project/Software/grl/src/grl/addons/rbdl/cfg/leo_vc',
            '/grl/src/grl/addons/rbdl/cfg/leo_vc',
            )

    models, names = create_models(model_paths)
    tasks, names = create_tasks(models, names)

    args['cl_depth'] = 2

    options = {'balancing_tf': '', 'balancing': 'nnload_rbload', 'walking': 'nnload_rbload'}
    starting_task = 'balancing_tf'
    mp_cfgs = []
    for task, name in zip(tasks, names):
        misc = {'tasks':task, 'starting_task':starting_task, 'runs':runs}

        export_names = "eq_curriculum_network_depth_" + str(args['cl_depth'])
        nn_params = (export_names, "{}_stat.pkl".format(export_names))
        mp_cfgs += do_network_based_leo(args, cores, name='ddpg-cl_short_'+name, nn_params=nn_params, options=options, **misc)

    #    mp_cfgs += do_steps_based(args, cores, name='ddpg-bbw', steps=(20000, 30000, 250000), **misc)
    #    mp_cfgs += do_steps_based(args, cores, name='ddpg-bw',  steps=(   -1, 50000, 250000), **misc)
    #    mp_cfgs += do_steps_based(args, cores, name='ddpg-w',   steps=(   -1,    -1, 300000), **misc)
    #
    #    # naive switching after achieving the balancing for n number of seconds happening twice. 0 means not used
    #    mp_cfgs += do_reach_timeout_based(args, cores, name='ddpg-rb55', reach_timeout=(5.0, 5.0, 0.0), **misc)
    #    mp_cfgs += do_reach_timeout_based(args, cores, name='ddpg-rb5', reach_timeout=(-1.0, 5.0, 0.0), **misc)
    #
    #    mp_cfgs += do_reach_timeout_based(args, cores, name='ddpg-rb2020', reach_timeout=(20.0, 20.0, 0.0), **misc)
    #    mp_cfgs += do_reach_timeout_based(args, cores, name='ddpg-rb20', reach_timeout=(-1.0, 20.0, 0.0), **misc)


    #    # walker2d
    #    tasks = {
    #        'balancing_tf': 'RoboschoolWalker2dBalancingGRL_TF-v1',
    #        'balancing':    'RoboschoolWalker2dBalancingGRL-v1',
    #        'walking':      'RoboschoolWalker2dGRL-v1'
    #        }
    #    misc = {'tasks':tasks, 'starting_task':starting_task, 'runs':runs}
    #    mp_cfgs += do_network_based_mujoco(args, cores, name='ddpg-cl_short_walker2d', nn_params=nn_params, **misc)


    # DBG: export configuration
    export_cfg(mp_cfgs)

    # Run all scripts at once
    random.shuffle(mp_cfgs)
    prepare_multiprocessing()
#    do_multiprocessing_pool(cores, mp_cfgs)
    config, tasks, starting_task = mp_cfgs[0]
    cl_run(tasks, starting_task, **config)


def do_steps_based(base_args, cores, name, steps, runs, tasks, starting_task):
    args = base_args.copy()
    args['steps'] = steps

    hp = Helper(args, 'cl', name, tasks, starting_task, cores, use_mp=True)

    # Weights of the NN
    solutions = [None]*len(runs)
    begin = runs[0]

    mp_cfgs = hp.gen_cfg(solutions, 1, begin=begin)
    return mp_cfgs


def do_reach_timeout_based(base_args, cores, name, reach_timeout, runs, tasks, starting_task):
    args = base_args.copy()
    args['reach_timeout'] = reach_timeout
    args['steps'] = 300000

    hp = Helper(args, 'cl', name, tasks, starting_task, cores, use_mp=True)

    # Weights of the NN
    solutions = [None]*len(runs)
    begin = runs[0]

    mp_cfgs = hp.gen_cfg(solutions, 1, begin=begin)
    return mp_cfgs


def do_network_based_mujoco(base_args, cores, name, nn_params, runs, tasks, starting_task):
    args = base_args.copy()
    args['env_td_error_scale'] = 600.0
    args['env_timeout'] = 16.5
    args['steps'] = 700000
    return do_network_based_leo(args, cores, name, nn_params, runs, tasks, starting_task)


def do_network_based_leo(base_args, cores, name, nn_params, options, runs, tasks, starting_task):
    args = base_args.copy()
    args['rb_min_size'] = 1000
    args['default_damage'] = 4035.00
    args['perf_td_error'] = True
    args['perf_l2_reg'] = True
    args['steps'] = 300000
    args["cl_batch_norm"] = False
    args['cl_structure'] = 'rnnc:gru_tanh_6_dropout;fc_linear_3'
    args['cl_stages'] = 'balancing_tf;balancing;walking:monotonic'
    args['cl_depth'] = 2
    args['cl_pt_shape'] = (2,3)
    args["cl_pt_load"] = nn_params[1]
    cl_load = nn_params[0]

    if options:
        suffix = ''
        if options['balancing_tf']:
            suffix += '1_' + options['balancing_tf'] + '_'
        if options['balancing']:
            suffix += '2_' + options['balancing'] + '_'
        if options['walking']:
            suffix += '3_' + options['walking']
        if suffix:
            name += '-' + suffix
        args['options'] = options

    hp = Helper(args, 'cl', name, tasks, starting_task, cores, use_mp=True)

    # Weights of the NN
    solutions = [None]*len(runs)
    begin = runs[0]

    mp_cfgs = hp.gen_cfg(solutions, 1, begin=begin)
    mp_cfgs_new = []
    for cfg in mp_cfgs:
        config, tasks, starting_task = cfg
        copy_config = config.copy()
        copy_config["cl_load"] = cl_load
        mp_cfgs_new.append( (copy_config, tasks, starting_task) )
    return mp_cfgs_new



def export_cfg(mp_cfgs):
    for cfg in mp_cfgs:
        config, tasks, starting_task = cfg
        with io.open(config['output']+'.yaml', 'w', encoding='utf8') as file:
            yaml.dump(config, file, default_flow_style=False, allow_unicode=True)


######################################################################################
######################################################################################
def create_models(paths):
    for path in paths:
        if os.path.isdir(path):
            break

    ppath = '/~perturbed~'
    if not os.path.exists(path+ppath):
        os.makedirs(path+ppath)

    files = {
            'tf': '{}{}/leo_ff_dl{}_tf.lua',
            'no': '{}{}/leo_ff_dl{}.lua',
            }

    torsoMass = 0.94226
    torsoMassPro = np.arange(-3, +4) * 0.1
    jointFriction = np.arange(0, +7) * 0.005

    content = {}
    for key in files:
        with open(files[key].format(path, '', ''), 'r') as content_file:
            content[key] = content_file.read()

    models = []
    names = []
    for tmp in torsoMassPro:
        model = {}
        for key in content:
            filename, file_extension = os.path.splitext(files[key].format(path,ppath,'_perturbed'))
            foutname = '{}_tm_{:.03f}{}'.format(filename, tmp, file_extension)
            with open(foutname, 'w') as fout:
                new_mass = 'torsoMass = {}'.format(torsoMass*(1+tmp))
                fout.write( content[key].replace('torsoMass = 0.94226', new_mass) )
            if key == 'tf':
                model['balancing_tf'] = foutname
            else:
                model['balancing'] = model['walking'] = foutname
        models.append(model)
        names.append('tm_{:.03f}'.format(tmp))

    for tmp in jointFriction:
        model = {}
        for key in content:
            filename, file_extension = os.path.splitext(files[key].format(path,ppath,'_perturbed'))
            foutname = '{}_jf_{:.03f}{}'.format(filename, tmp, file_extension)
            with open(foutname, 'w') as fout:
                new_mass = 'jointFriction = {}'.format(tmp)
                fout.write( content[key].replace('jointFriction = 0.00', new_mass) )
            if key == 'tf':
                model['balancing_tf'] = foutname
            else:
                model['balancing'] = model['walking'] = foutname
        models.append(model)
        names.append('jf_{:.03f}'.format(tmp))
    return models, names


def create_tasks(models, names):

    if not os.path.exists('cfg/perturbed/'):
        os.makedirs('cfg/perturbed/')

    itasks = {
        'balancing_tf': 'cfg/leo_balancing_tf.yaml',
        'balancing':    'cfg/leo_balancing.yaml',
        'walking':      'cfg/leo_walking.yaml'
        }

    otasks = []
    for model, name in zip(models,names):
        task = {}
        for key in itasks:
            conf = read_cfg(itasks[key])
            conf['environment']['environment']['model']['dynamics']['file'] = model[key]
            path, filename = os.path.split(itasks[key])
            filename, file_extension = os.path.splitext(filename)
            fullname = path + '/perturbed/' + filename + '_' + name + file_extension
            write_cfg(fullname, conf)
            task[key] = fullname
        otasks.append(task)

    return otasks, names

######################################################################################
######################################################################################

def read_cfg(cfg):
    """Read configuration file"""
    # check if file exists
    yfile = cfg
    if os.path.isfile(yfile) == False:
        print('File %s not found' % yfile)
        sys.exit()

    # open configuration
    stream = open(yfile, 'r')
    conf = yaml.load(stream)
    stream.close()
    return conf
######################################################################################

def write_cfg(outCfg, conf):
    """Write configuration file"""
    # create local yaml configuration file
    outfile = open(outCfg, 'w')
    yaml.dump(conf, outfile)
    outfile.close()
######################################################################################

def remove_viz(conf):
    """Remove everything in conf related to visualization"""
    if "visualize" in conf['experiment']['environment']:
        conf['experiment']['environment']['visualize'] = 0
    if "target_env" in conf['experiment']['environment']:
    	if "visualize" in conf['experiment']['environment']['target_env']:
        	conf['experiment']['environment']['target_env']['visualize'] = 0
    if "visualizer" in conf:
            del conf["visualizer"]
    if "visualization" in conf:
            del conf["visualization"]
    if "visualization2" in conf:
            del conf["visualization2"]
    return conf
######################################################################################

def dict_representer(dumper, data):
  return dumper.represent_dict(data.items())
######################################################################################

def dict_constructor(loader, node):
  return collections.OrderedDict(loader.construct_pairs(node))

######################################################################################
######################################################################################

if __name__ == "__main__":
    main()
